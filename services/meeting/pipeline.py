"""Checkpointed transcription stage. Later stages extend this pipeline."""

import hashlib
import json
import os
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
        from .adapters.asr import transcribe_audio
        config = json.loads(job["model_config_json"])
        def progress(ms: int) -> None:
            if not store.heartbeat(job["id"], worker_id, ms):
                raise RuntimeError("Job lease lost during transcription")

        result = transcribe_audio(decoded, asset, config, progress=progress)
        _write_checkpoint(checkpoint, job, asset, result)
    store.save_segments(job, worker_id, result["segments"])
