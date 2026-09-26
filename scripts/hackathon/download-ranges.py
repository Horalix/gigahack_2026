"""Resumable parallel download for pinned public Hugging Face model files."""

import argparse
import hashlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests


CHUNK_BYTES = 1024 * 1024
WORKERS = 24


def signed_location(hub_url: str) -> str:
    for attempt in range(5):
        try:
            response = requests.head(hub_url, allow_redirects=False, timeout=(10, 20))
            response.raise_for_status()
            if response.status_code not in (302, 307) or not response.headers.get("Location"):
                raise RuntimeError("Expected a signed Hugging Face model download URL")
            return response.headers["Location"]
        except requests.RequestException:
            if attempt == 4:
                raise
            time.sleep(attempt + 1)
    raise RuntimeError("Could not resolve the pinned model download URL")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("hub_url")
    parser.add_argument("destination", type=Path)
    parser.add_argument("size_bytes", type=int)
    parser.add_argument("sha256")
    args = parser.parse_args()
    if args.size_bytes < 1 or len(args.sha256) != 64:
        parser.error("Expected pinned size and SHA-256")
    destination = args.destination.resolve()
    marker = destination.with_name(destination.name + ".ranges.json")
    count = (args.size_bytes + CHUNK_BYTES - 1) // CHUNK_BYTES
    if marker.is_file() and destination.is_file() and destination.stat().st_size == args.size_bytes:
        progress = json.loads(marker.read_text(encoding="utf-8"))
        if progress.get("sizeBytes") != args.size_bytes or progress.get("sha256") != args.sha256:
            raise RuntimeError("Partial model download belongs to a different artifact")
        done = set(progress.get("done", []))
    else:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("wb") as output:
            output.truncate(args.size_bytes)
        done = set()
    if any(not isinstance(index, int) or index < 0 or index >= count for index in done):
        raise RuntimeError("Partial model progress file is invalid")

    lock = threading.Lock()
    sessions = threading.local()
    location = signed_location(args.hub_url)

    def fetch(index: int) -> int:
        nonlocal location
        start = index * CHUNK_BYTES
        end = min(args.size_bytes, start + CHUNK_BYTES) - 1
        if not hasattr(sessions, "client"):
            sessions.client = requests.Session()
        for attempt in range(8):
            with lock:
                current_location = location
            try:
                response = sessions.client.get(current_location, headers={"Range": f"bytes={start}-{end}"}, timeout=(10, 30))
            except requests.RequestException:
                time.sleep(min(attempt + 1, 5))
                continue
            if response.status_code == 403:
                with lock:
                    if current_location == location:
                        location = signed_location(args.hub_url)
                continue
            if response.status_code in (429, 500, 502, 503, 504):
                time.sleep(min(attempt + 1, 5))
                continue
            response.raise_for_status()
            if response.status_code != 206 or response.headers.get("Content-Range", "").split("/")[0] != f"bytes {start}-{end}" or len(response.content) != end - start + 1:
                raise RuntimeError(f"Model range {index} returned unexpected bytes")
            with destination.open("r+b") as output:
                output.seek(start)
                output.write(response.content)
                output.flush()
                os.fsync(output.fileno())
            return index
        raise RuntimeError(f"Model range {index} could not be downloaded")

    outstanding = (index for index in range(count) if index not in done)
    failures = []
    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(fetch, index): index for index in outstanding}
        for future in as_completed(futures):
            try:
                index = future.result()
            except Exception as exc:
                failures.append((futures[future], exc))
                continue
            done.add(index)
            progress = {"sizeBytes": args.size_bytes, "sha256": args.sha256, "done": sorted(done)}
            temporary = marker.with_name(marker.name + ".tmp")
            temporary.write_text(json.dumps(progress, separators=(",", ":")), encoding="utf-8")
            os.replace(temporary, marker)
            if len(done) % 128 == 0 or len(done) == count:
                print(f"Pinned model download: {len(done)}/{count} MiB", flush=True)

    if failures:
        raise RuntimeError(f"{len(failures)} model ranges failed; rerun to resume") from failures[0][1]

    digest = hashlib.sha256()
    with destination.open("rb") as source:
        for chunk in iter(lambda: source.read(4 * CHUNK_BYTES), b""):
            digest.update(chunk)
    if digest.hexdigest() != args.sha256:
        marker.unlink(missing_ok=True)
        raise RuntimeError("Pinned model SHA-256 verification failed; rerun to fetch every range")
    marker.unlink(missing_ok=True)
    print("Pinned model SHA-256 verified", flush=True)


if __name__ == "__main__":
    main()
