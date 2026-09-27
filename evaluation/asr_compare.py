"""Small local Whisper/OmniASR comparison for the Medpark Romanian recording.

Run inside the prepared WSL environment; inputs and raw hypotheses stay outside Git.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import unicodedata
import wave
from pathlib import Path


WINDOW_SECONDS = 30
WINDOWS = {
    "whisper-ro": ("whisper-ro", ""),
    "omni-ctc-1b": ("omni-ctc", "omniASR_CTC_1B_v2"),
    "omni-llm-1b-ro": ("omni-llm", "omniASR_LLM_1B_v2"),
}


def digest(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).casefold()
    return " ".join("".join(ch if unicodedata.category(ch)[0] in "LMN" else " " for ch in text).split())


def edit_distance(left: list[str] | str, right: list[str] | str) -> int:
    previous = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        current = [i]
        for j, b in enumerate(right, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (a != b)))
        previous = current
    return previous[-1]


def score(reference: str, hypothesis: str) -> dict:
    ref = normalize(reference)
    hyp = normalize(hypothesis)
    ref_words, hyp_words = ref.split(), hyp.split()
    if not ref_words:
        raise ValueError("The saved reference is empty after normalization")
    return {
        "wer": edit_distance(ref_words, hyp_words) / len(ref_words),
        "werEdits": edit_distance(ref_words, hyp_words),
        "referenceWords": len(ref_words),
        "cer": edit_distance(ref.replace(" ", ""), hyp.replace(" ", "")) / max(1, len(ref.replace(" ", ""))),
        "referenceCharacters": len(ref.replace(" ", "")),
    }


def create_windows(audio: Path, directory: Path) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    with wave.open(str(audio), "rb") as src:
        if (src.getnchannels(), src.getframerate(), src.getsampwidth()) != (1, 16000, 2):
            raise ValueError("Input must be the frozen 16 kHz mono PCM16 WAV")
        rate = src.getframerate()
        frames_per_window = rate * WINDOW_SECONDS
        index, paths = 0, []
        while audio_bytes := src.readframes(frames_per_window):
            path = directory / f"window-{index:03d}.wav"
            with wave.open(str(path), "wb") as dst:
                dst.setnchannels(1)
                dst.setsampwidth(2)
                dst.setframerate(rate)
                dst.writeframes(audio_bytes)
            paths.append(path)
            index += 1
    return paths


def run_worker(root: Path, model: str, model_path: Path, windows: list[Path], *, warm: bool) -> dict:
    result_path = root / "runs" / f"{model}{'-warm' if warm else ''}.json"
    result_path.parent.mkdir(parents=True, exist_ok=True)
    selected_windows = windows[:1] if warm else windows
    command = [sys.executable, str(Path(__file__).with_name("asr_compare_worker.py")),
               "--model", WINDOWS[model][0], "--model-path", str(model_path), "--output", str(result_path),
               *map(str, selected_windows)]
    if model.startswith("omni-"):
        # Let fairseq2 use its user cache; no model or input is stored in the repository.
        pass
    print(f"{'Warm-up' if warm else 'Run'} {model}: {len(selected_windows)} windows", flush=True)
    env = os.environ.copy()
    site_packages = Path(sys.prefix) / "lib" / f"python{sys.version_info.major}.{sys.version_info.minor}" / "site-packages"
    cuda_libs = sorted(str(path) for path in (site_packages / "nvidia").glob("*/lib") if path.is_dir())
    if cuda_libs:
        env["LD_LIBRARY_PATH"] = ":".join(cuda_libs + ([env["LD_LIBRARY_PATH"]] if env.get("LD_LIBRARY_PATH") else []))
    subprocess.run(command, check=True, env=env)
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["modelId"] = model
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True, help="Private WSL directory outside Git")
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--whisper-model", type=Path, required=True)
    parser.add_argument("--models", nargs="+", choices=WINDOWS, default=list(WINDOWS))
    args = parser.parse_args()
    root = args.root.resolve()
    audio, reference = args.audio.resolve(), args.reference.resolve()
    if not audio.is_file() or not reference.is_file():
        parser.error("Audio and reference files must both exist")
    windows = create_windows(audio, root / "windows")
    ref_text = reference.read_text(encoding="utf-8")
    source_hash, ref_hash = digest(audio), digest(reference)
    reports = {}
    for model in args.models:
        model_path = args.whisper_model.resolve() if model == "whisper-ro" else Path(WINDOWS[model][1])
        run_worker(root, model, model_path, windows, warm=True)
        result = run_worker(root, model, model_path, windows, warm=False)
        result["metrics"] = score(ref_text, result["text"])
        result["audioSha256"] = source_hash
        result["referenceSha256"] = ref_hash
        result["windowSeconds"] = WINDOW_SECONDS
        output = root / "runs" / f"{model}.json"
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        reports[model] = result
        metrics = result["metrics"]
        print(f"{model}: WER={metrics['wer']:.4f} CER={metrics['cer']:.4f} "
              f"wall={result['wallSeconds']:.1f}s ASR-RTF={result['rtf']:.4f}", flush=True)
    (root / "summary.json").write_text(json.dumps(reports, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
