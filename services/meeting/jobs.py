"""One-at-a-time offline worker with lease renewal and restart recovery."""

import argparse
import logging
import os
import threading
import time
import uuid

from .pipeline import process_job
from .storage import Storage


log = logging.getLogger(__name__)


def run_once(store: Storage, worker_id: str | None = None) -> bool:
    store.flush_file_cleanup()
    owner = worker_id or str(uuid.uuid4())
    job = store.claim_job(owner)
    if job is None:
        return False
    stopped = threading.Event()
    lost_lease = threading.Event()

    def renew() -> None:
        while not stopped.wait(5):
            try:
                if not store.heartbeat(job["id"], owner):
                    lost_lease.set()
                    return
            except Exception:
                log.exception("Job lease renewal failed for job %s", job["id"])
                lost_lease.set()
                return

    thread = threading.Thread(target=renew, name="meeting-job-heartbeat", daemon=True)
    thread.start()
    try:
        process_job(store, job, owner)
        if lost_lease.is_set() or not store.finish_job(job["id"], owner, "ready"):
            raise RuntimeError("Job lease was lost before completion")
    except Exception as exc:
        code = getattr(exc, "code", None) or "PROCESSING_FAILED"
        message = str(exc) if code != "PROCESSING_FAILED" else "Processing failed; check local worker logs"
        store.finish_job(job["id"], owner, "failed", code, message[:300])
        log.exception("Job %s failed", job["id"])
    finally:
        stopped.set()
        thread.join(timeout=6)
        store.flush_file_cleanup()
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Local Secure MOM job worker")
    parser.add_argument("--once", action="store_true", help="Process at most one queued job")
    parser.add_argument("--poll-seconds", type=float, default=1.0)
    args = parser.parse_args()
    if args.poll_seconds <= 0:
        parser.error("--poll-seconds must be positive")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    store = Storage()
    worker_id = f"{os.getpid()}-{uuid.uuid4()}"
    while True:
        found = run_once(store, worker_id)
        if args.once:
            break
        if not found:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
