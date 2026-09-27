"""Single-model child process so model memory is returned when the run exits."""

from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from pathlib import Path


def gpu_memory_mib() -> int | None:
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                                capture_output=True, check=True, timeout=2)
        return max(int(value) for value in result.stdout.decode().splitlines())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", choices=("whisper-ro", "omni-ctc", "omni-llm"), required=True)
    parser.add_argument("--model-path", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("windows", nargs="+", type=Path)
    args = parser.parse_args()
    stop = threading.Event()
    peak_gpu = gpu_memory_mib()

    def monitor() -> None:
        nonlocal peak_gpu
        while not stop.wait(0.5):
            current = gpu_memory_mib()
            if current is not None:
                peak_gpu = max(peak_gpu or 0, current)

    watcher = threading.Thread(target=monitor, daemon=True)
    watcher.start()
    started = time.perf_counter()
    if args.model == "whisper-ro":
        from faster_whisper import WhisperModel
        load_start = time.perf_counter()
        model = WhisperModel(str(args.model_path), device="cuda", compute_type="int8_float16", local_files_only=True)
        load_seconds = time.perf_counter() - load_start
        infer_start = time.perf_counter()
        texts = []
        for path in args.windows:
            segments, _info = model.transcribe(str(path), task="transcribe", language="ro", multilingual=False,
                beam_size=5, word_timestamps=True, vad_filter=False, condition_on_previous_text=False)
            texts.append("".join(segment.text for segment in segments).strip())
    else:
        import torch
        from omnilingual_asr.models.inference.pipeline import ASRInferencePipeline
        load_start = time.perf_counter()
        pipeline = ASRInferencePipeline(model_card=str(args.model_path), device="cuda", dtype=torch.bfloat16)
        load_seconds = time.perf_counter() - load_start
        torch.cuda.synchronize()
        infer_start = time.perf_counter()
        texts = []
        for path in args.windows:
            languages = ["ron_Latn"] if args.model == "omni-llm" else None
            texts.extend(pipeline.transcribe([str(path)], lang=languages, batch_size=1))
        torch.cuda.synchronize()
    infer_seconds = time.perf_counter() - infer_start
    wall_seconds = time.perf_counter() - started
    stop.set()
    watcher.join(timeout=3)
    import wave
    audio_seconds = sum(wave.open(str(path), "rb").getnframes() / 16000 for path in args.windows)
    result = {
        "model": args.model,
        "modelCard": str(args.model_path),
        "device": "CUDA / bfloat16" if args.model.startswith("omni-") else "CUDA / int8_float16",
        "windowCount": len(texts),
        "audioSeconds": round(audio_seconds, 3),
        "loadSeconds": round(load_seconds, 3),
        "inferenceSeconds": round(infer_seconds, 3),
        "wallSeconds": round(wall_seconds, 3),
        "rtf": round(wall_seconds / max(audio_seconds, 0.001), 5),
        "peakGpuUsedMiB": peak_gpu,
        "text": " ".join(texts),
        "windowTexts": texts,
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Completed {args.model}: {audio_seconds:.1f}s audio in {wall_seconds:.1f}s", flush=True)


if __name__ == "__main__":
    main()
