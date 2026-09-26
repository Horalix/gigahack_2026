"""Offline faster-whisper transcription with source-aligned timings."""

import gc
import subprocess
import threading
import time
from pathlib import Path
from typing import Callable


class ASRError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def _gpu_memory_mib() -> int | None:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=2, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        return max(int(line.strip()) for line in result.stdout.decode().splitlines())
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return None


def transcribe_audio(decoded: Path, asset: dict, config: dict, progress: Callable[[int], object] | None = None) -> dict:
    """Consume the entire recognizer iterator before returning durable raw segments."""
    selected = config["models"]["asr"]
    model_path = Path(selected["path"]).expanduser().resolve() if selected.get("path") else None
    if model_path is None or not model_path.is_dir() or not (model_path / "model.bin").is_file():
        raise ASRError("MODEL_NOT_READY", "The selected local ASR model is missing")
    if selected.get("backend") != "faster_whisper":
        raise ASRError("ASR_BACKEND_UNSUPPORTED", "The selected ASR backend is unavailable")
    if not decoded.is_file():
        raise ASRError("DECODED_AUDIO_MISSING", "Decoded audio is missing")

    if selected.get("artifacts"):
        from ..models import ModelAssetError, ModelConfigurationError, validate_assets
        try:
            validate_assets(config, kinds=("asr",))
        except (ModelAssetError, ModelConfigurationError) as exc:
            raise ASRError("MODEL_NOT_READY", "The pinned local ASR assets failed verification") from exc

    from faster_whisper import BatchedInferencePipeline, WhisperModel
    import ctranslate2

    device = selected.get("device", "cuda")
    try:
        supported = ctranslate2.get_supported_compute_types(device)
    except (RuntimeError, ValueError) as exc:
        raise ASRError("ASR_DEVICE_UNAVAILABLE", "The selected ASR device is unavailable") from exc
    if selected.get("compute_type", "int8_float16") not in supported:
        raise ASRError("ASR_PRECISION_UNSUPPORTED", "The selected ASR precision is unsupported")
    batch_size = int(selected.get("batch_size", 1))
    started = time.perf_counter()
    peak_gpu = _gpu_memory_mib() if device == "cuda" else None
    stop = threading.Event()

    def sample_gpu() -> None:
        nonlocal peak_gpu
        while not stop.wait(1):
            value = _gpu_memory_mib()
            if value is not None:
                peak_gpu = max(peak_gpu or 0, value)

    monitor = threading.Thread(target=sample_gpu, daemon=True) if device == "cuda" else None
    if monitor:
        monitor.start()
    model = None
    try:
        model = WhisperModel(str(model_path), device=device,
                             compute_type=selected.get("compute_type", "int8_float16"),
                             cpu_threads=int(selected.get("cpu_threads", 0)), local_files_only=True)
        engine = BatchedInferencePipeline(model) if batch_size > 1 else model
        options = {
            "task": "transcribe", "language": None, "multilingual": True,
            "beam_size": int(selected.get("beam_size", 5)),
            "word_timestamps": bool(selected.get("word_timestamps", True)),
            "vad_filter": True,
            "vad_parameters": {"min_silence_duration_ms": 500, "speech_pad_ms": 250},
            "condition_on_previous_text": False,
        }
        if batch_size > 1:
            options["batch_size"] = batch_size
        iterator, info = engine.transcribe(str(decoded), **options)
        source_offset = int(asset.get("source_offset_ms", 0))
        source_duration = int(asset["duration_ms"])
        raw = []
        for index, segment in enumerate(iterator):
            start = max(0, round(segment.start * 1000) + source_offset)
            end = min(source_duration, round(segment.end * 1000) + source_offset)
            if not segment.text or end <= start:
                continue
            words = []
            for word in segment.words or []:
                word_start = max(start, round(word.start * 1000) + source_offset)
                word_end = min(end, round(word.end * 1000) + source_offset)
                if word_end > word_start:
                    words.append({"startMs": word_start, "endMs": word_end, "text": word.word,
                                  "probability": word.probability})
            raw.append({"id": f"{asset['id']}-seg-{index:06d}", "transcriptRevision": 1,
                        "startMs": start, "endMs": end, "text": segment.text,
                        "language": "und", "origin": "asr", "speakerClusterId": None,
                        "words": words})
            if progress:
                progress(end)
        if progress:
            progress(source_duration)
        metrics = {"audioDurationMs": source_duration,
                   "wallSeconds": round(time.perf_counter() - started, 3),
                   "peakGpuMemoryMiBObserved": peak_gpu,
                   "gpuMemoryMeasurement": "nvidia-smi total used on device; includes other processes" if peak_gpu is not None else None,
                   "detectedLanguage": info.language if info else None,
                   "modelPath": str(model_path), "device": device,
                   "computeType": selected.get("compute_type"), "beamSize": options["beam_size"],
                   "batchSize": batch_size, "wordTimestamps": options["word_timestamps"]}
        return {"segments": raw, "metrics": metrics}
    except ASRError:
        raise
    except RuntimeError as exc:
        if "out of memory" in str(exc).casefold():
            raise ASRError("ASR_OUT_OF_MEMORY", "The selected ASR model exceeded available GPU memory") from exc
        raise ASRError("ASR_RUNTIME_FAILED", "Local ASR execution failed") from exc
    finally:
        stop.set()
        if monitor:
            monitor.join(timeout=3)
        del model
        gc.collect()
