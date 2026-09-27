"""Checkpointed offline transcription and evidence-backed decision pipeline."""

import hashlib
import json
import os
import wave
import uuid
from pathlib import Path

from .storage import Storage


def _checkpoint_path(store: Storage, job: dict) -> Path:
    return store.asset_path(job["meeting_id"], job["id"], ".transcript.json")


def _read_checkpoint(path: Path, job: dict, asset: dict) -> dict | None:
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    config_hash = hashlib.sha256(job["model_config_json"].encode()).hexdigest()
    if (data.get("jobId") != job["id"] or data.get("assetSha256") != asset["source_sha256"]
            or data.get("configSha256") != config_hash or not isinstance(data.get("segments"), list)):
        raise RuntimeError("Transcript checkpoint does not match the job and source asset")
    return data


def _write_checkpoint(path: Path, job: dict, asset: dict, result: dict) -> None:
    temporary = path.with_name(path.name + f".{uuid.uuid4().hex}.tmp")
    data = {"jobId": job["id"], "assetSha256": asset["source_sha256"],
            "configSha256": hashlib.sha256(job["model_config_json"].encode()).hexdigest(),
            "segments": result["segments"], "metrics": result["metrics"]}
    try:
        with temporary.open("x", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, separators=(",", ":"))
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _write_audio_range(source_path: Path, destination: Path, asset: dict,
                       start_ms: int, end_ms: int) -> None:
    source_offset = int(asset.get("source_offset_ms", 0))
    start_frame = max(0, round((start_ms - source_offset) * 16))
    end_frame = max(start_frame, round((end_ms - source_offset) * 16))
    with wave.open(str(source_path), "rb") as source:
        if (source.getnchannels(), source.getsampwidth(), source.getframerate(), source.getcomptype()) != (1, 2, 16000, "NONE"):
            raise RuntimeError("Decoded source is not mono PCM16 at 16 kHz")
        end_frame = min(end_frame, source.getnframes())
        source.setpos(start_frame)
        with wave.open(str(destination), "wb") as output:
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(16000)
            remaining = end_frame - start_frame
            while remaining:
                frames = source.readframes(min(remaining, 480_000))
                if not frames:
                    break
                output.writeframesraw(frames)
                remaining -= len(frames) // 2
            if remaining:
                raise RuntimeError("Could not read the complete uncovered audio range")


def _transcribe_with_capture_previews(store: Storage, job: dict, asset: dict, decoded: Path,
                                      config: dict, progress) -> dict:
    from .adapters.asr import asr_configuration_hash, transcribe_audio

    windows = store.get_capture_preview_windows(
        asset["id"], job["organization_id"], asr_configuration_hash(config))
    if not windows:
        return transcribe_audio(decoded, asset, config, progress=progress)

    duration_ms = int(asset["duration_ms"])
    source_offset_ms = int(asset.get("source_offset_ms", 0))
    cursor = source_offset_ms
    all_segments = []
    preview_wall_seconds = 0.0
    preview_peak_gpu = None
    preview_coverage_ms = 0
    gap_metrics = []
    temp_dir = store.root / "runtime-tmp" / "live-asr"
    temp_dir.mkdir(parents=True, exist_ok=True)

    def add_segments(segments: list[dict], source_key: str) -> None:
        for index, segment in enumerate(segments):
            item = dict(segment)
            item["id"] = str(uuid.uuid5(uuid.NAMESPACE_URL,
                f"notavra-asr:{job['id']}:{source_key}:{index}"))
            item["transcriptRevision"] = 1
            all_segments.append(item)

    def bounded_preview_segments(segments: list[dict], start_ms: int, end_ms: int) -> list[dict]:
        bounded = []
        for segment in segments:
            words = segment.get("words") or []
            if words:
                selected = [dict(word) for word in words
                            if start_ms <= (word["startMs"] + word["endMs"]) // 2 < end_ms]
                if not selected:
                    continue
                for word in selected:
                    word["startMs"] = max(start_ms, word["startMs"])
                    word["endMs"] = min(end_ms, word["endMs"])
                bounded.append({**segment, "startMs": min(word["startMs"] for word in selected),
                                "endMs": max(word["endMs"] for word in selected),
                                "text": "".join(word["text"] for word in selected), "words": selected})
            elif start_ms <= (segment["startMs"] + segment["endMs"]) // 2 < end_ms:
                bounded.append({**segment, "startMs": max(start_ms, segment["startMs"]),
                                "endMs": min(end_ms, segment["endMs"])})
        return bounded

    def transcribe_gap(start_ms: int, end_ms: int) -> None:
        if end_ms <= start_ms:
            return
        gap_path = temp_dir / f"{uuid.uuid4()}.wav"
        try:
            _write_audio_range(decoded, gap_path, asset, start_ms, end_ms)
            result = transcribe_audio(gap_path,
                {**asset, "id": f"{asset['id']}-gap-{start_ms}", "source_offset_ms": start_ms},
                config, progress=progress)
            add_segments(result["segments"], f"gap:{start_ms}")
            gap_metrics.append(result["metrics"])
        finally:
            gap_path.unlink(missing_ok=True)

    valid_windows = []
    for window in windows:
        start = int(window["start_ms"])
        end = min(duration_ms, int(window["ownership_end_ms"]))
        if source_offset_ms <= start < end <= duration_ms:
            valid_windows.append((window, start, end))
    for index, (window, start, end) in enumerate(valid_windows):
        if start < cursor:
            continue
        transcribe_gap(cursor, start)
        add_segments(bounded_preview_segments(window["segments"], start, end), f"window:{start}")
        preview_wall_seconds += float(window["wall_seconds"])
        peak = window.get("peak_gpu_memory_mib")
        if peak is not None:
            preview_peak_gpu = max(preview_peak_gpu or 0, int(peak))
        preview_coverage_ms += end - start
        cursor = end
        if progress:
            progress(end)
    transcribe_gap(cursor, duration_ms)

    metrics = {
        "audioDurationMs": duration_ms,
        "wallSeconds": round(preview_wall_seconds + sum(float(item.get("wallSeconds", 0)) for item in gap_metrics), 3),
        "peakGpuMemoryMiBObserved": max(
            [value for value in [preview_peak_gpu, *(item.get("peakGpuMemoryMiBObserved") for item in gap_metrics)] if value is not None],
            default=None),
        "gpuMemoryMeasurement": "nvidia-smi total used on device; includes other processes" if preview_peak_gpu is not None or any(item.get("peakGpuMemoryMiBObserved") is not None for item in gap_metrics) else None,
        "detectedLanguage": config["models"]["asr"].get("language"),
        "modelPath": config["models"]["asr"].get("path"),
        "device": config["models"]["asr"].get("device"),
        "computeType": config["models"]["asr"].get("compute_type"),
        "beamSize": config["models"]["asr"].get("beam_size"),
        "batchSize": config["models"]["asr"].get("batch_size"),
        "wordTimestamps": config["models"]["asr"].get("word_timestamps"),
        "livePreviewWindowsReused": len(valid_windows),
        "livePreviewCoverageMs": preview_coverage_ms,
        "uncoveredGapCount": len(gap_metrics),
    }
    return {"segments": all_segments, "metrics": metrics}


def process_job(store: Storage, job: dict, worker_id: str) -> None:
    asset = store.get_asset(job["asset_id"], job["organization_id"])
    if asset is None:
        raise RuntimeError("Source asset record is missing")
    source = store.resolve_key(asset["source_key"])
    decoded = store.resolve_key(asset["decoded_key"])
    if not source.is_file() or not decoded.is_file():
        raise RuntimeError("Saved source or decoded audio is missing")
    checkpoint = _checkpoint_path(store, job)
    result = _read_checkpoint(checkpoint, job, asset)
    if result is None:
        config = json.loads(job["model_config_json"])
        def progress(ms: int) -> None:
            if not store.heartbeat(job["id"], worker_id, ms):
                raise RuntimeError("Job lease lost during transcription")

        result = _transcribe_with_capture_previews(store, job, asset, decoded, config, progress)
        _write_checkpoint(checkpoint, job, asset, result)
    store.save_segments(job, worker_id, result["segments"])

    if store.get_job_decisions(job["id"], job["organization_id"]) is None:
        from .decisions import extract_decisions

        if not store.set_job_stage(job["id"], worker_id, "extract"):
            raise RuntimeError("Job lease lost before local decision extraction")
        meeting = store.get_meeting(job["meeting_id"], job["organization_id"])
        if meeting is None:
            raise RuntimeError("Meeting record is missing")
        decision_job = {**job, "model_config": json.loads(job["model_config_json"])}

        def decision_progress() -> None:
            if not store.heartbeat(job["id"], worker_id):
                raise RuntimeError("Job lease lost during decision extraction")

        decisions = extract_decisions(
            store.get_segments(job["meeting_id"], job["organization_id"]), meeting,
            decision_job, store.root / "runtime-tmp", progress=decision_progress,
        )
        store.save_decisions(job, worker_id, decisions)
