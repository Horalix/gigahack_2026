"""Cross-process admission for the single local inference device."""

from contextlib import contextmanager
import os
from pathlib import Path
import time


class InferenceBusy(RuntimeError):
    pass


@contextmanager
def inference_device_lock(data_root: Path, wait_seconds: float = 0):
    """Serialize worker and preview inference across the API/worker processes."""
    lock_dir = data_root / "locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with (lock_dir / "inference.lock").open("a+b") as stream:
        stream.seek(0, os.SEEK_END)
        if stream.tell() == 0:
            stream.write(b"\0")
            stream.flush()
        deadline = time.monotonic() + wait_seconds
        while True:
            try:
                if os.name == "nt":
                    import msvcrt

                    stream.seek(0)
                    msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if time.monotonic() >= deadline:
                    raise InferenceBusy("Local inference device is busy")
                time.sleep(0.1)
        try:
            yield
        finally:
            if os.name == "nt":
                import msvcrt

                stream.seek(0)
                msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(stream.fileno(), fcntl.LOCK_UN)
