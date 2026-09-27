"""Durable, ordered chunk capture for browser MediaRecorder sessions."""

import hashlib
import os
from .media import MAX_UPLOAD_BYTES, MediaError, decode
from .storage import MAX_CAPTURE_BYTES, Storage


class CaptureError(RuntimeError):
    def __init__(self, code: str, message: str, *, status: int = 422):
        super().__init__(message)
        self.code = code
        self.status = status


def seal_capture(store: Storage, session_id: str, organization_id: str,
                 actor_id: str, expected_sequence_count: int) -> dict:
    """Reassemble contiguous WebM/MP4 chunks, decode them, then atomically publish the asset."""
    try:
        capture = store.begin_capture_seal(session_id, organization_id, actor_id, expected_sequence_count)
    except LookupError as exc:
        raise CaptureError("CAPTURE_NOT_FOUND", "Capture not found", status=404) from exc
    except ValueError as exc:
        raise CaptureError("CAPTURE_INCOMPLETE", str(exc), status=409) from exc
    if capture["state"] == "sealed":
        if capture.get("asset"):
            return capture["asset"]
        raise CaptureError("CAPTURE_ASSET_MISSING", "The sealed audio asset is missing", status=409)

    source = store.asset_path(capture["meeting_id"], capture["asset_id"], ".source")
    decoded = store.asset_path(capture["meeting_id"], capture["asset_id"], ".wav")
    temporary = source.with_name(source.name + ".assembling")
    temporary.unlink(missing_ok=True)
    digest = hashlib.sha256()
    size = 0
    try:
        with temporary.open("xb") as output:
            for chunk in capture["chunks"]:
                path = store.resolve_key(chunk["storage_key"])
                with path.open("rb") as part:
                    while data := part.read(1024 * 1024):
                        size += len(data)
                        if size > min(MAX_CAPTURE_BYTES, MAX_UPLOAD_BYTES):
                            raise CaptureError("CAPTURE_TOO_LARGE", "Capture exceeds the 2 GiB limit", status=413)
                        digest.update(data)
                        output.write(data)
            output.flush()
            os.fsync(output.fileno())
        if size == 0:
            raise CaptureError("CAPTURE_EMPTY", "The microphone recording is empty")
        os.replace(temporary, source)
        try:
            media = decode(source, decoded)
        except MediaError as exc:
            raise CaptureError(exc.code, str(exc)) from exc
        details = {"id": capture["asset_id"], "source_key": store.relative_key(source),
                   "decoded_key": store.relative_key(decoded), "source_sha256": digest.hexdigest(),
                   "size_bytes": size, "media_type": capture["content_type"], **media}
        return store.complete_capture(session_id, organization_id, actor_id, details)
    except CaptureError as exc:
        store.fail_capture(session_id, exc.code)
        source.unlink(missing_ok=True)
        decoded.unlink(missing_ok=True)
        raise
    except (OSError, ValueError) as exc:
        store.fail_capture(session_id, "CAPTURE_STORAGE_FAILED")
        source.unlink(missing_ok=True)
        decoded.unlink(missing_ok=True)
        raise CaptureError("CAPTURE_STORAGE_FAILED", "Captured audio could not be sealed", status=507) from exc
    finally:
        temporary.unlink(missing_ok=True)
