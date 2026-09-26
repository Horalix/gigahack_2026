"""Durable meeting records and a single GPU job lease in SQLite."""

import json
import os
import sqlite3
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


LEASE_SECONDS = 30
SCHEMA_VERSION = 3


def default_data_root() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_DATA_HOME")
    if base:
        return Path(base) / "SecureMOM"
    return Path.home() / ".local" / "share" / "secure-mom"


def timestamp(value: float | None = None) -> str:
    return datetime.fromtimestamp(value if value is not None else time.time(), timezone.utc).isoformat().replace("+00:00", "Z")


class Storage:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or os.environ.get("MOM_DATA_DIR") or default_data_root()).expanduser().resolve()
        workspace = Path(__file__).resolve().parents[2]
        if self.root.is_relative_to(workspace) or any(part.casefold() == "onedrive" for part in self.root.parts):
            raise ValueError("Meeting data directory must be outside the repository and OneDrive")
        self.root.mkdir(parents=True, exist_ok=True)
        self.assets_dir = self.root / "assets"
        self.assets_dir.mkdir(exist_ok=True)
        self.db_path = self.root / "meetings.sqlite3"
        self._migrate()

    def connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.db_path, timeout=5, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        db.execute("PRAGMA synchronous=FULL")
        return db

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        db = self.connect()
        try:
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def _migrate(self) -> None:
        with closing(self.connect()) as db:
            db.execute("PRAGMA journal_mode=WAL")
        with self.transaction() as db:
            current = db.execute("PRAGMA user_version").fetchone()[0]
            if current > SCHEMA_VERSION:
                raise RuntimeError("Database schema is newer than this service")
            if current < 1:
                statements = """
                CREATE TABLE meetings (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, title TEXT NOT NULL,
                    recorded_at TEXT NOT NULL, time_zone TEXT NOT NULL, output_language TEXT NOT NULL,
                    meeting_type TEXT, status TEXT NOT NULL, transcript_revision INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE TABLE assets (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, meeting_id TEXT NOT NULL REFERENCES meetings(id),
                    source_key TEXT NOT NULL, source_sha256 TEXT NOT NULL, decoded_key TEXT NOT NULL,
                    duration_ms INTEGER NOT NULL, source_offset_ms INTEGER NOT NULL, size_bytes INTEGER NOT NULL,
                    media_type TEXT NOT NULL, audio_track_index INTEGER NOT NULL, channels INTEGER,
                    sample_rate_hz INTEGER, created_at TEXT NOT NULL
                );
                CREATE INDEX assets_meeting ON assets(meeting_id, created_at);
                CREATE TABLE jobs (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, meeting_id TEXT NOT NULL REFERENCES meetings(id),
                    asset_id TEXT NOT NULL REFERENCES assets(id), state TEXT NOT NULL, stage TEXT NOT NULL,
                    profile_id TEXT NOT NULL, model_config_json TEXT NOT NULL,
                    error_code TEXT, error_message TEXT, progress_ms INTEGER NOT NULL DEFAULT 0,
                    attempts INTEGER NOT NULL DEFAULT 0, lease_owner TEXT, lease_until REAL,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                );
                CREATE INDEX jobs_state ON jobs(state, created_at);
                CREATE UNIQUE INDEX one_active_job_per_asset ON jobs(asset_id) WHERE state IN ('queued', 'running');
                CREATE TABLE segments (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, meeting_id TEXT NOT NULL REFERENCES meetings(id),
                    asset_id TEXT NOT NULL REFERENCES assets(id), job_id TEXT NOT NULL REFERENCES jobs(id),
                    transcript_revision INTEGER NOT NULL, start_ms INTEGER NOT NULL, end_ms INTEGER NOT NULL,
                    text TEXT NOT NULL, language TEXT NOT NULL, origin TEXT NOT NULL,
                    words_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE INDEX segments_meeting_time ON segments(meeting_id, transcript_revision, start_ms);
            """
                for statement in statements.split(";"):
                    if statement.strip():
                        db.execute(statement)
                db.execute("PRAGMA user_version=1")
            if current < 2:
                db.execute("ALTER TABLE assets ADD COLUMN kind TEXT NOT NULL DEFAULT 'audio'")
                db.execute("PRAGMA user_version=2")
            if current < 3:
                db.execute("ALTER TABLE assets ADD COLUMN decode_warning TEXT")
                db.execute("PRAGMA user_version=3")

    def asset_path(self, meeting_id: str, asset_id: str, suffix: str) -> Path:
        # IDs are generated locally; never put an uploaded name into a filesystem path.
        path = self.assets_dir / meeting_id / f"{asset_id}{suffix}"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def relative_key(self, path: Path) -> str:
        return path.resolve().relative_to(self.root).as_posix()

    def resolve_key(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError("Storage key escapes data directory")
        return path

    def create_meeting(self, principal: dict, data: dict) -> dict:
        now = timestamp()
        row = {
            "id": str(uuid.uuid4()), "organization_id": principal["organization_id"],
            "title": data["title"], "recorded_at": data["recordedAt"],
            "time_zone": data["timeZone"], "output_language": data["outputLanguage"],
            "meeting_type": data.get("meetingType"), "status": "draft", "transcript_revision": 0,
            "created_at": now, "updated_at": now,
        }
        with self.transaction() as db:
            db.execute("""INSERT INTO meetings
                (id, organization_id, title, recorded_at, time_zone, output_language, meeting_type,
                 status, transcript_revision, created_at, updated_at)
                VALUES (:id, :organization_id, :title, :recorded_at, :time_zone, :output_language,
                        :meeting_type, :status, :transcript_revision, :created_at, :updated_at)""", row)
        return row

    def get_meeting(self, meeting_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM meetings WHERE id=? AND organization_id=?", (meeting_id, organization_id)).fetchone()
            return dict(row) if row else None

    def create_asset(self, meeting_id: str, organization_id: str, details: dict) -> dict:
        row = {"id": details["id"], "organization_id": organization_id, "meeting_id": meeting_id,
               "source_key": details["source_key"], "source_sha256": details["source_sha256"],
               "decoded_key": details["decoded_key"], "duration_ms": details["duration_ms"],
               "source_offset_ms": details["source_offset_ms"], "size_bytes": details["size_bytes"],
               "media_type": details["media_type"], "audio_track_index": details["audio_track_index"],
               "channels": details.get("channels"), "sample_rate_hz": details.get("sample_rate_hz"),
               "created_at": timestamp(), "kind": details["kind"],
               "decode_warning": details.get("decode_warning")}
        with self.transaction() as db:
            db.execute("""INSERT INTO assets
                (id,organization_id,meeting_id,source_key,source_sha256,decoded_key,duration_ms,
                 source_offset_ms,size_bytes,media_type,audio_track_index,channels,sample_rate_hz,created_at,kind,decode_warning)
                 VALUES (:id,:organization_id,:meeting_id,:source_key,:source_sha256,:decoded_key,
                 :duration_ms,:source_offset_ms,:size_bytes,:media_type,:audio_track_index,
                 :channels,:sample_rate_hz,:created_at,:kind,:decode_warning)""", row)
        return row

    def latest_asset(self, meeting_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM assets WHERE meeting_id=? AND organization_id=? ORDER BY created_at DESC, id DESC LIMIT 1", (meeting_id, organization_id)).fetchone()
            return dict(row) if row else None

    def get_asset(self, asset_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM assets WHERE id=? AND organization_id=?", (asset_id, organization_id)).fetchone()
            return dict(row) if row else None

    def create_or_get_job(self, meeting_id: str, organization_id: str, asset_id: str, config: dict) -> dict:
        with self.transaction() as db:
            config_json = json.dumps(config, sort_keys=True)
            existing = db.execute("""SELECT * FROM jobs WHERE meeting_id=? AND organization_id=? AND asset_id=?
                AND (state IN ('queued','running') OR (state='ready' AND model_config_json=?))
                ORDER BY created_at DESC LIMIT 1""",
                (meeting_id, organization_id, asset_id, config_json)).fetchone()
            if existing:
                return dict(existing)
            now = timestamp()
            row = {"id": str(uuid.uuid4()), "organization_id": organization_id, "meeting_id": meeting_id,
                   "asset_id": asset_id, "state": "queued", "stage": "transcribe",
                   "profile_id": config["profile_id"], "model_config_json": config_json,
                   "error_code": None, "error_message": None, "progress_ms": 0, "attempts": 0,
                   "lease_owner": None, "lease_until": None, "created_at": now, "updated_at": now}
            db.execute("""INSERT INTO jobs VALUES
                (:id,:organization_id,:meeting_id,:asset_id,:state,:stage,:profile_id,:model_config_json,
                 :error_code,:error_message,:progress_ms,:attempts,:lease_owner,:lease_until,:created_at,:updated_at)""", row)
            db.execute("UPDATE meetings SET status='processing',updated_at=? WHERE id=?", (now, meeting_id))
            return row

    def get_job(self, job_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND organization_id=?", (job_id, organization_id)).fetchone()
            return dict(row) if row else None

    def claim_job(self, worker_id: str) -> dict | None:
        now = time.time()
        with self.transaction() as db:
            expired = db.execute("SELECT id FROM jobs WHERE state='running' AND lease_until<=?", (now,)).fetchall()
            for row in expired:
                db.execute("UPDATE jobs SET state='queued',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?", (timestamp(now), row["id"]))
            busy = db.execute("SELECT 1 FROM jobs WHERE state='running' AND lease_until>? LIMIT 1", (now,)).fetchone()
            if busy:
                return None
            row = db.execute("SELECT * FROM jobs WHERE state='queued' ORDER BY created_at,id LIMIT 1").fetchone()
            if not row:
                return None
            db.execute("""UPDATE jobs SET state='running',lease_owner=?,lease_until=?,attempts=attempts+1,
                error_code=NULL,error_message=NULL,updated_at=? WHERE id=?""",
                (worker_id, now + LEASE_SECONDS, timestamp(now), row["id"]))
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (row["id"],)).fetchone())

    def heartbeat(self, job_id: str, worker_id: str, progress_ms: int | None = None) -> bool:
        with self.transaction() as db:
            result = db.execute("""UPDATE jobs SET lease_until=?, progress_ms=MAX(progress_ms,?), updated_at=?
                WHERE id=? AND state='running' AND lease_owner=?""",
                (time.time() + LEASE_SECONDS, progress_ms or 0, timestamp(), job_id, worker_id))
            return result.rowcount == 1

    def finish_job(self, job_id: str, worker_id: str, state: str, error_code: str | None = None, error_message: str | None = None) -> bool:
        with self.transaction() as db:
            job = db.execute("SELECT * FROM jobs WHERE id=? AND state='running' AND lease_owner=?", (job_id, worker_id)).fetchone()
            if not job:
                return False
            now = timestamp()
            db.execute("""UPDATE jobs SET state=?,stage=?,error_code=?,error_message=?,lease_owner=NULL,
                lease_until=NULL,updated_at=? WHERE id=?""",
                (state, "complete" if state == "ready" else job["stage"], error_code, error_message, now, job_id))
            meeting_state = "transcript_ready" if state == "ready" else state
            db.execute("UPDATE meetings SET status=?,updated_at=? WHERE id=?", (meeting_state, now, job["meeting_id"]))
            return True

    def retry_job(self, job_id: str, organization_id: str) -> dict | None:
        with self.transaction() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=? AND organization_id=? AND state='failed'", (job_id, organization_id)).fetchone()
            if not row:
                return None
            if db.execute("SELECT 1 FROM jobs WHERE asset_id=? AND state IN ('queued','running') LIMIT 1", (row["asset_id"],)).fetchone():
                return None
            db.execute("""UPDATE jobs SET state='queued',error_code=NULL,error_message=NULL,
                lease_owner=NULL,lease_until=NULL,updated_at=? WHERE id=?""", (timestamp(), job_id))
            db.execute("UPDATE meetings SET status='processing',updated_at=? WHERE id=?", (timestamp(), row["meeting_id"]))
            return dict(db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone())

    def save_segments(self, job: dict, worker_id: str, segments: list[dict]) -> None:
        with self.transaction() as db:
            lease = db.execute("SELECT lease_owner,state FROM jobs WHERE id=?", (job["id"],)).fetchone()
            if not lease or lease["lease_owner"] != worker_id or lease["state"] != "running":
                raise RuntimeError("Job lease lost before transcript commit")
            prior = db.execute("SELECT transcript_revision FROM segments WHERE job_id=? LIMIT 1", (job["id"],)).fetchone()
            if prior:
                revision = prior["transcript_revision"]
            else:
                current = db.execute("SELECT transcript_revision FROM meetings WHERE id=?", (job["meeting_id"],)).fetchone()[0]
                revision = current + 1
            db.execute("DELETE FROM segments WHERE job_id=?", (job["id"],))
            for segment in segments:
                db.execute("""INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (segment["id"], job["organization_id"], job["meeting_id"], job["asset_id"], job["id"],
                     revision, segment["startMs"], segment["endMs"], segment["text"],
                     segment["language"], segment["origin"], json.dumps(segment.get("words", []), ensure_ascii=False), timestamp()))
            db.execute("UPDATE meetings SET transcript_revision=?,updated_at=? WHERE id=?", (revision, timestamp(), job["meeting_id"]))

    def get_segments(self, meeting_id: str, organization_id: str) -> list[dict]:
        with closing(self.connect()) as db:
            rows = db.execute("""SELECT s.* FROM segments s JOIN meetings m ON m.id=s.meeting_id
                WHERE s.meeting_id=? AND m.organization_id=? AND s.transcript_revision=m.transcript_revision
                ORDER BY s.start_ms,s.id""", (meeting_id, organization_id)).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["words"] = json.loads(item.pop("words_json"))
                result.append(item)
            return result
