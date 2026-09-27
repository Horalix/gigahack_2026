"""Run the app's exact Whisper adapter on the private Medpark WAV, Romanian forced."""

import argparse
import json
import wave
from pathlib import Path

from evaluation.asr_compare import digest, score
from services.meeting.adapters.asr import transcribe_audio
from services.meeting.models import resolve_profile


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with wave.open(str(args.audio), "rb") as audio:
        duration_ms = round(audio.getnframes() * 1000 / audio.getframerate())
    result = transcribe_audio(args.audio, {"id": "medpark-native", "duration_ms": duration_ms,
                                           "source_offset_ms": 0},
                              resolve_profile("laptop8", overrides={"asr": {"language": "ro"}}))
    text = " ".join(segment["text"] for segment in result["segments"])
    performance = result.pop("metrics")
    result.update({
        "model": "Whisper large-v3 / app adapter / Romanian forced",
        "audioSha256": digest(args.audio),
        "referenceSha256": digest(args.reference),
        "metrics": score(args.reference.read_text(encoding="utf-8"), text),
        "performance": performance,
        "text": text,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    metric = result["metrics"]
    print(f"Whisper native Romanian: WER={metric['wer']:.4f} CER={metric['cer']:.4f} "
          f"wall={performance['wallSeconds']:.1f}s RTF={performance['wallSeconds'] / (duration_ms / 1000):.4f}")


if __name__ == "__main__":
    main()
