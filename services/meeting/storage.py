"""Durable meeting records and a single GPU job lease in SQLite."""

import json
import hashlib
import os
import sqlite3
import tempfile
import time
import uuid
from contextlib import closing, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


LEASE_SECONDS = 30
MAX_CAPTURE_BYTES = 2 * 1024 * 1024 * 1024
SCHEMA_VERSION = 11


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
            if current < 4:
                legacy_org = db.execute("SELECT organization_id FROM meetings ORDER BY created_at LIMIT 1").fetchone()
                org_id = legacy_org["organization_id"] if legacy_org else f"org-{uuid.uuid4()}"
                db.execute("CREATE TABLE installation (singleton INTEGER PRIMARY KEY CHECK(singleton=1), organization_id TEXT NOT NULL)")
                db.execute("INSERT INTO installation(singleton,organization_id) VALUES(1,?)", (org_id,))
                db.execute("""CREATE TABLE users (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, username TEXT NOT NULL,
                    password_hash TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('clinician','reviewer','administrator')),
                    active INTEGER NOT NULL DEFAULT 1 CHECK(active IN (0,1)), created_at TEXT NOT NULL,
                    UNIQUE(organization_id,username))""")
                db.execute("CREATE TABLE auth_sessions (token_hash TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL, expires_at REAL NOT NULL, revoked_at TEXT)")
                db.execute("""CREATE TABLE meeting_grants (
                    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                    organization_id TEXT NOT NULL, user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                    permission TEXT NOT NULL CHECK(permission IN ('owner','editor','viewer')),
                    granted_by TEXT NOT NULL REFERENCES users(id), created_at TEXT NOT NULL,
                    PRIMARY KEY(meeting_id,user_id))""")
                db.execute("CREATE INDEX meeting_grants_user ON meeting_grants(organization_id,user_id,meeting_id)")
                db.execute("CREATE INDEX auth_sessions_user ON auth_sessions(user_id,expires_at)")
                db.execute("PRAGMA user_version=4")
            if current < 5:
                db.execute("""CREATE TABLE decision_results (
                    job_id TEXT PRIMARY KEY REFERENCES jobs(id) ON DELETE CASCADE,
                    organization_id TEXT NOT NULL, meeting_id TEXT NOT NULL REFERENCES meetings(id),
                    transcript_revision INTEGER NOT NULL, result_json TEXT NOT NULL, created_at TEXT NOT NULL
                )""")
                db.execute("CREATE INDEX decision_results_meeting ON decision_results(meeting_id,transcript_revision,created_at)")
                db.execute("PRAGMA user_version=5")
            if current < 6:
                db.execute("""CREATE TABLE segment_revisions (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, meeting_id TEXT NOT NULL REFERENCES meetings(id),
                    segment_id TEXT NOT NULL REFERENCES segments(id), editor_id TEXT NOT NULL REFERENCES users(id),
                    from_revision INTEGER NOT NULL, to_revision INTEGER NOT NULL,
                    old_text TEXT NOT NULL, new_text TEXT NOT NULL, created_at TEXT NOT NULL
                )""")
                db.execute("CREATE INDEX segment_revisions_meeting ON segment_revisions(meeting_id,created_at)")
                db.execute("PRAGMA user_version=6")
            if current < 7:
                db.execute("""CREATE TABLE patients (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL,
                    display_name TEXT NOT NULL, search_name TEXT NOT NULL,
                    hospital_reference TEXT, search_reference TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL CHECK(status IN ('active','inactive')),
                    created_by TEXT NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
                db.execute("CREATE INDEX patients_org_name ON patients(organization_id,search_name,id)")
                db.execute("CREATE INDEX patients_org_reference ON patients(organization_id,search_reference,id)")
                db.execute("""CREATE TABLE patient_meetings (
                    patient_id TEXT NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
                    meeting_id TEXT NOT NULL REFERENCES meetings(id) ON DELETE CASCADE,
                    organization_id TEXT NOT NULL, linked_by TEXT NOT NULL REFERENCES users(id),
                    created_at TEXT NOT NULL, PRIMARY KEY(patient_id,meeting_id)
                )""")
                db.execute("CREATE INDEX patient_meetings_meeting ON patient_meetings(organization_id,meeting_id,patient_id)")
                db.execute("PRAGMA user_version=7")
            if current < 8:
                db.execute("""CREATE TABLE artifacts (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL,
                    meeting_id TEXT NOT NULL REFERENCES meetings(id), transcript_revision INTEGER NOT NULL,
                    decision_sha256 TEXT NOT NULL, storage_key TEXT NOT NULL UNIQUE,
                    mime_type TEXT NOT NULL, sha256 TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN ('ready','superseded','revoked')),
                    approved_by TEXT NOT NULL REFERENCES users(id), approved_at TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )""")
                db.execute("CREATE INDEX artifacts_meeting_revision ON artifacts(meeting_id,transcript_revision,created_at)")
                db.execute("PRAGMA user_version=8")
            if current < 9:
                db.execute("""CREATE TABLE capture_sessions (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL,
                    meeting_id TEXT NOT NULL REFERENCES meetings(id), asset_id TEXT NOT NULL UNIQUE,
                    created_by TEXT NOT NULL REFERENCES users(id), content_type TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('capturing','sealing','sealed','failed')),
                    next_sequence INTEGER NOT NULL DEFAULT 0, received_bytes INTEGER NOT NULL DEFAULT 0,
                    error_code TEXT, created_at TEXT NOT NULL, updated_at TEXT NOT NULL
                )""")
                db.execute("CREATE INDEX capture_sessions_meeting ON capture_sessions(organization_id,meeting_id,created_at)")
                db.execute("""CREATE TABLE capture_chunks (
                    session_id TEXT NOT NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
                    sequence INTEGER NOT NULL, storage_key TEXT NOT NULL UNIQUE,
                    size_bytes INTEGER NOT NULL, sha256 TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(session_id,sequence)
                )""")
                db.execute("PRAGMA user_version=9")
            if current < 10:
                db.execute("""CREATE TABLE deletion_audit (
                    id TEXT PRIMARY KEY, organization_id TEXT NOT NULL, actor_id TEXT NOT NULL,
                    subject_type TEXT NOT NULL, subject_id TEXT NOT NULL, action TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )""")
                db.execute("CREATE INDEX deletion_audit_org_time ON deletion_audit(organization_id,created_at)")
                db.execute("""CREATE TABLE file_cleanup (
                    storage_key TEXT PRIMARY KEY, queued_at TEXT NOT NULL
                )""")
                db.execute("PRAGMA user_version=10")
            if current < 11:
                db.execute("""CREATE TABLE capture_preview_windows (
                    session_id TEXT NOT NULL REFERENCES capture_sessions(id) ON DELETE CASCADE,
                    start_ms INTEGER NOT NULL, ownership_end_ms INTEGER NOT NULL,
                    asr_config_sha256 TEXT NOT NULL, segments_json TEXT NOT NULL,
                    wall_seconds REAL NOT NULL, peak_gpu_memory_mib INTEGER,
                    created_at TEXT NOT NULL, PRIMARY KEY(session_id,start_ms)
                )""")
                db.execute("CREATE INDEX capture_preview_config ON capture_preview_windows(asr_config_sha256,session_id,start_ms)")
                db.execute("PRAGMA user_version=11")

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
            db.execute("""INSERT INTO meeting_grants
                (meeting_id,organization_id,user_id,permission,granted_by,created_at)
                VALUES(?,?,?,'owner',?,?)""",
                (row["id"], row["organization_id"], principal["id"], principal["id"], now))
            for patient_id in dict.fromkeys(data.get("patientLinkIds", [])):
                patient = db.execute("""SELECT p.id FROM patients p WHERE p.id=? AND p.organization_id=? AND
                    (p.created_by=? OR EXISTS (SELECT 1 FROM patient_meetings pm
                      JOIN meeting_grants mg ON mg.meeting_id=pm.meeting_id AND mg.organization_id=pm.organization_id
                      WHERE pm.patient_id=p.id AND pm.organization_id=p.organization_id
                        AND mg.user_id=? AND mg.organization_id=?))""",
                    (patient_id, row["organization_id"], principal["id"], principal["id"],
                     row["organization_id"])).fetchone()
                if not patient:
                    raise ValueError("A selected patient is unavailable")
                db.execute("""INSERT INTO patient_meetings
                    (patient_id,meeting_id,organization_id,linked_by,created_at) VALUES(?,?,?,?,?)""",
                    (patient_id, row["id"], row["organization_id"], principal["id"], now))
        return row

    def meeting_patient_ids(self, meeting_id: str, organization_id: str) -> list[str]:
        with closing(self.connect()) as db:
            rows = db.execute("SELECT patient_id FROM patient_meetings WHERE meeting_id=? AND organization_id=? ORDER BY patient_id",
                              (meeting_id, organization_id)).fetchall()
            return [row["patient_id"] for row in rows]

    def create_artifact(self, meeting_id: str, organization_id: str, actor_id: str,
                        transcript_revision: int, decisions: dict, content: bytes) -> dict | None:
        artifact_id = str(uuid.uuid4())
        directory = self.root / "artifacts" / meeting_id
        directory.mkdir(parents=True, exist_ok=True)
        destination = directory / f"{artifact_id}.html"
        temporary = None
        committed = False
        decision_json = json.dumps(decisions, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        decision_digest = hashlib.sha256(decision_json.encode("utf-8")).hexdigest()
        digest = hashlib.sha256(content).hexdigest()
        now = timestamp()
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=directory, prefix=f".{artifact_id}-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            with self.transaction() as db:
                meeting = db.execute("SELECT transcript_revision FROM meetings WHERE id=? AND organization_id=?",
                                     (meeting_id, organization_id)).fetchone()
                permission = db.execute("SELECT permission FROM meeting_grants WHERE meeting_id=? AND organization_id=? AND user_id=?",
                                        (meeting_id, organization_id, actor_id)).fetchone()
                decision_row = db.execute("""SELECT d.result_json FROM decision_results d JOIN jobs j
                    ON j.id=d.job_id AND j.state='ready' JOIN meetings m ON m.id=d.meeting_id
                    WHERE d.meeting_id=? AND d.organization_id=? AND d.transcript_revision=m.transcript_revision
                    ORDER BY d.created_at DESC,d.job_id DESC LIMIT 1""", (meeting_id, organization_id)).fetchone()
                if (not meeting or meeting["transcript_revision"] != transcript_revision or
                        not permission or permission["permission"] not in {"owner", "editor"} or not decision_row):
                    return None
                current_json = json.dumps(json.loads(decision_row["result_json"]), ensure_ascii=False,
                                          sort_keys=True, separators=(",", ":"))
                if hashlib.sha256(current_json.encode("utf-8")).hexdigest() != decision_digest:
                    return None
                os.replace(temporary, destination)
                temporary = None
                row = {"id": artifact_id, "organization_id": organization_id, "meeting_id": meeting_id,
                       "transcript_revision": transcript_revision, "decision_sha256": decision_digest,
                       "storage_key": self.relative_key(destination), "mime_type": "text/html; charset=utf-8",
                       "sha256": digest, "status": "ready", "approved_by": actor_id,
                       "approved_at": now, "created_at": now}
                db.execute("""INSERT INTO artifacts
                    (id,organization_id,meeting_id,transcript_revision,decision_sha256,storage_key,mime_type,sha256,
                     status,approved_by,approved_at,created_at)
                    VALUES(:id,:organization_id,:meeting_id,:transcript_revision,:decision_sha256,:storage_key,:mime_type,:sha256,
                           :status,:approved_by,:approved_at,:created_at)""", row)
            committed = True
            return row
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
            if not committed:
                destination.unlink(missing_ok=True)

    def latest_artifact(self, meeting_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("""SELECT a.* FROM artifacts a JOIN meetings m ON m.id=a.meeting_id
                WHERE a.meeting_id=? AND a.organization_id=? AND a.status='ready'
                  AND a.transcript_revision=m.transcript_revision
                ORDER BY a.created_at DESC,a.id DESC LIMIT 1""", (meeting_id, organization_id)).fetchone()
            return dict(row) if row else None

    def get_artifact(self, artifact_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM artifacts WHERE id=? AND organization_id=?",
                             (artifact_id, organization_id)).fetchone()
            return dict(row) if row else None

    def artifact_path(self, storage_key: str) -> Path:
        path = self.resolve_key(storage_key)
        if not path.is_file():
            raise FileNotFoundError("Artifact file is missing")
        return path

    def purge_meeting(self, meeting_id: str, organization_id: str, actor_id: str) -> int | None:
        """Revoke a meeting and all app-managed derivatives; return cleanup queue size."""
        with self.transaction() as db:
            meeting = db.execute("""SELECT m.id,g.permission FROM meetings m JOIN meeting_grants g
                ON g.meeting_id=m.id AND g.organization_id=m.organization_id
                WHERE m.id=? AND m.organization_id=? AND g.user_id=?""",
                (meeting_id, organization_id, actor_id)).fetchone()
            if not meeting or meeting["permission"] != "owner":
                return None
            db.execute("UPDATE jobs SET state='cancelled',stage='cancelled',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE meeting_id=? AND state='queued'",
                       (timestamp(), meeting_id))
            active = db.execute("SELECT 1 FROM jobs WHERE meeting_id=? AND state='running' LIMIT 1",
                                (meeting_id,)).fetchone()
            if active:
                # In-flight model processes may still hold source files open. Refuse deletion
                # until inference reaches its next lease check and releases those files.
                raise RuntimeError("MEETING_PROCESSING")
            job_ids = [row["id"] for row in db.execute("SELECT id FROM jobs WHERE meeting_id=?", (meeting_id,))]
            paths = set()
            for row in db.execute("SELECT source_key,decoded_key FROM assets WHERE meeting_id=?", (meeting_id,)):
                paths.update((row["source_key"], row["decoded_key"]))
            asset_directory = self.assets_dir / meeting_id
            if asset_directory.is_dir():
                paths.update(self.relative_key(path) for path in asset_directory.rglob("*") if path.is_file())
            for job_id in job_ids:
                paths.add(self.relative_key(self.asset_path(meeting_id, job_id, ".transcript.json")))
            paths.update(row["storage_key"] for row in db.execute(
                "SELECT storage_key FROM artifacts WHERE meeting_id=?", (meeting_id,)))
            for capture in db.execute("SELECT id FROM capture_sessions WHERE meeting_id=?", (meeting_id,)):
                directory = self.root / "captures" / capture["id"]
                if directory.is_dir():
                    paths.update(self.relative_key(path) for path in directory.iterdir() if path.is_file())
            db.execute("DELETE FROM segment_revisions WHERE meeting_id=?", (meeting_id,))
            db.execute("DELETE FROM segments WHERE meeting_id=?", (meeting_id,))
            db.execute("DELETE FROM artifacts WHERE meeting_id=?", (meeting_id,))
            db.execute("DELETE FROM capture_sessions WHERE meeting_id=?", (meeting_id,))
            db.execute("DELETE FROM jobs WHERE meeting_id=?", (meeting_id,))
            db.execute("DELETE FROM assets WHERE meeting_id=?", (meeting_id,))
            db.execute("DELETE FROM patient_meetings WHERE meeting_id=?", (meeting_id,))
            db.execute("DELETE FROM meeting_grants WHERE meeting_id=?", (meeting_id,))
            db.execute("DELETE FROM meetings WHERE id=?", (meeting_id,))
            for key in paths:
                db.execute("INSERT OR IGNORE INTO file_cleanup(storage_key,queued_at) VALUES(?,?)",
                           (key, timestamp()))
            db.execute("""INSERT INTO deletion_audit
                (id,organization_id,actor_id,subject_type,subject_id,action,created_at)
                VALUES(?,?,?,?,?,?,?)""",
                (str(uuid.uuid4()), organization_id, actor_id, "meeting", meeting_id, "purge_requested", timestamp()))
        return self.flush_file_cleanup()

    def flush_file_cleanup(self) -> int:
        """Best-effort unlink queued files; locked files remain queued for retry."""
        removed = 0
        with closing(self.connect()) as db:
            keys = [row["storage_key"] for row in db.execute("SELECT storage_key FROM file_cleanup")]
        for key in keys:
            try:
                self.resolve_key(key).unlink(missing_ok=True)
            except (OSError, ValueError):
                continue
            with self.transaction() as db:
                db.execute("DELETE FROM file_cleanup WHERE storage_key=?", (key,))
            removed += 1
        for parent in (self.root / "artifacts", self.root / "captures", self.assets_dir):
            if parent.exists():
                for directory in sorted((path for path in parent.rglob("*") if path.is_dir()), reverse=True):
                    try:
                        directory.rmdir()
                    except OSError:
                        pass
        with closing(self.connect()) as db:
            pending = db.execute("SELECT COUNT(*) FROM file_cleanup").fetchone()[0]
        if pending == 0:
            with closing(self.connect()) as db:
                db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return pending

    def installation_organization(self) -> str:
        with closing(self.connect()) as db:
            return db.execute("SELECT organization_id FROM installation WHERE singleton=1").fetchone()[0]

    def create_user(self, organization_id: str, username: str, password_hash: str, role: str, *, bootstrap: bool = False) -> dict:
        now = timestamp()
        row = {"id": str(uuid.uuid4()), "organization_id": organization_id, "username": username,
               "password_hash": password_hash, "role": role, "active": 1, "created_at": now}
        with self.transaction() as db:
            if bootstrap and db.execute("SELECT 1 FROM users LIMIT 1").fetchone():
                raise ValueError("Initial administrator already exists")
            try:
                db.execute("""INSERT INTO users(id,organization_id,username,password_hash,role,active,created_at)
                    VALUES(:id,:organization_id,:username,:password_hash,:role,:active,:created_at)""", row)
            except sqlite3.IntegrityError as exc:
                raise ValueError("Username is already provisioned") from exc
            if bootstrap:
                db.execute("""INSERT INTO meeting_grants
                    (meeting_id,organization_id,user_id,permission,granted_by,created_at)
                    SELECT id,organization_id,?, 'owner', ?, ? FROM meetings WHERE organization_id=?""",
                    (row["id"], row["id"], now, organization_id))
        return row

    def user_count(self) -> int:
        with closing(self.connect()) as db:
            return db.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def get_user_by_username(self, username: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM users WHERE organization_id=(SELECT organization_id FROM installation WHERE singleton=1) AND username=?",
                             (username,)).fetchone()
            return dict(row) if row else None

    def get_user(self, user_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM users WHERE id=? AND organization_id=(SELECT organization_id FROM installation WHERE singleton=1)",
                             (user_id,)).fetchone()
            return dict(row) if row else None

    def list_users(self) -> list[dict]:
        with closing(self.connect()) as db:
            rows = db.execute("""SELECT id,organization_id,username,role,active,created_at FROM users
                WHERE organization_id=(SELECT organization_id FROM installation WHERE singleton=1)
                ORDER BY username,id""").fetchall()
            return [dict(row) for row in rows]

    def set_user_active(self, user_id: str, active: bool) -> bool:
        with self.transaction() as db:
            result = db.execute("""UPDATE users SET active=? WHERE id=?
                AND organization_id=(SELECT organization_id FROM installation WHERE singleton=1)""",
                (int(active), user_id))
            if result.rowcount:
                db.execute("UPDATE auth_sessions SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
                           (timestamp(), user_id))
            return result.rowcount == 1

    def update_password_hash(self, user_id: str, password_hash: str) -> None:
        with self.transaction() as db:
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (password_hash, user_id))

    def create_session(self, token_hash: str, user_id: str, lifetime_seconds: int) -> None:
        now = time.time()
        with self.transaction() as db:
            db.execute("DELETE FROM auth_sessions WHERE expires_at<=? OR revoked_at IS NOT NULL", (now,))
            db.execute("INSERT INTO auth_sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)",
                       (token_hash, user_id, timestamp(now), now + lifetime_seconds))

    def get_session_user(self, token_hash: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("""SELECT u.id,u.organization_id,u.username,u.role,u.active
                FROM auth_sessions s JOIN users u ON u.id=s.user_id
                WHERE s.token_hash=? AND s.revoked_at IS NULL AND s.expires_at>?""",
                (token_hash, time.time())).fetchone()
            return dict(row) if row and row["active"] else None

    def revoke_session(self, token_hash: str) -> None:
        with self.transaction() as db:
            db.execute("UPDATE auth_sessions SET revoked_at=? WHERE token_hash=? AND revoked_at IS NULL",
                       (timestamp(), token_hash))

    def meeting_permission(self, meeting_id: str, user_id: str, organization_id: str) -> str | None:
        with closing(self.connect()) as db:
            row = db.execute("""SELECT g.permission FROM meeting_grants g JOIN meetings m ON m.id=g.meeting_id
                WHERE g.meeting_id=? AND g.user_id=? AND g.organization_id=? AND m.organization_id=?""",
                (meeting_id, user_id, organization_id, organization_id)).fetchone()
            return row["permission"] if row else None

    def grant_meeting(self, meeting_id: str, organization_id: str, user_id: str,
                      permission: str, granted_by: str) -> bool:
        if permission not in {"editor", "viewer"}:
            raise ValueError("Grant permission must be editor or viewer")
        with self.transaction() as db:
            meeting = db.execute("SELECT 1 FROM meetings WHERE id=? AND organization_id=?",
                                 (meeting_id, organization_id)).fetchone()
            user = db.execute("SELECT 1 FROM users WHERE id=? AND organization_id=? AND active=1",
                              (user_id, organization_id)).fetchone()
            if not meeting or not user:
                return False
            db.execute("""INSERT INTO meeting_grants(meeting_id,organization_id,user_id,permission,granted_by,created_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(meeting_id,user_id) DO UPDATE SET
                permission=excluded.permission,granted_by=excluded.granted_by,created_at=excluded.created_at""",
                (meeting_id, organization_id, user_id, permission, granted_by, timestamp()))
            return True

    def meeting_grants(self, meeting_id: str, organization_id: str) -> list[dict]:
        with closing(self.connect()) as db:
            rows = db.execute("""SELECT g.user_id,g.permission,u.username,g.granted_by,g.created_at
                FROM meeting_grants g JOIN users u ON u.id=g.user_id
                WHERE g.meeting_id=? AND g.organization_id=? ORDER BY u.username""",
                (meeting_id, organization_id)).fetchall()
            return [dict(row) for row in rows]

    def revoke_meeting_grant(self, meeting_id: str, organization_id: str, user_id: str) -> bool:
        with self.transaction() as db:
            result = db.execute("""DELETE FROM meeting_grants WHERE meeting_id=? AND organization_id=?
                AND user_id=? AND permission!='owner'""", (meeting_id, organization_id, user_id))
            return result.rowcount == 1

    def get_meeting(self, meeting_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM meetings WHERE id=? AND organization_id=?", (meeting_id, organization_id)).fetchone()
            return dict(row) if row else None

    def list_meetings(self, user_id: str, organization_id: str, *, query: str = "", limit: int = 20, offset: int = 0) -> tuple[list[dict], int]:
        pattern = f"%{query.strip()}%"
        with closing(self.connect()) as db:
            where = "m.organization_id=? AND g.user_id=? AND m.title LIKE ?"
            total = db.execute(f"SELECT COUNT(*) FROM meetings m JOIN meeting_grants g ON g.meeting_id=m.id WHERE {where}",
                               (organization_id, user_id, pattern)).fetchone()[0]
            rows = db.execute(f"""SELECT m.* FROM meetings m JOIN meeting_grants g ON g.meeting_id=m.id
                WHERE {where} ORDER BY m.recorded_at DESC,m.id LIMIT ? OFFSET ?""",
                (organization_id, user_id, pattern, limit, offset)).fetchall()
            return [dict(row) for row in rows], total

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

    def create_capture_session(self, meeting_id: str, organization_id: str, actor_id: str,
                               content_type: str) -> dict:
        if content_type not in {"audio/webm", "audio/webm;codecs=opus", "audio/mp4", "audio/wav"}:
            raise ValueError("Unsupported microphone recording format")
        now, session_id, asset_id = timestamp(), str(uuid.uuid4()), str(uuid.uuid4())
        row = {"id": session_id, "organization_id": organization_id, "meeting_id": meeting_id,
               "asset_id": asset_id, "created_by": actor_id, "content_type": content_type,
               "state": "capturing", "next_sequence": 0, "received_bytes": 0,
               "error_code": None, "created_at": now, "updated_at": now}
        with self.transaction() as db:
            db.execute("""INSERT INTO capture_sessions
                (id,organization_id,meeting_id,asset_id,created_by,content_type,state,next_sequence,received_bytes,error_code,created_at,updated_at)
                VALUES(:id,:organization_id,:meeting_id,:asset_id,:created_by,:content_type,:state,:next_sequence,:received_bytes,:error_code,:created_at,:updated_at)""", row)
        return row

    def get_capture_session(self, session_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT * FROM capture_sessions WHERE id=? AND organization_id=?",
                             (session_id, organization_id)).fetchone()
            if not row:
                return None
            result = dict(row)
            chunks = db.execute("SELECT * FROM capture_chunks WHERE session_id=? ORDER BY sequence",
                                (session_id,)).fetchall()
            result["chunks"] = [dict(chunk) for chunk in chunks]
            return result

    def list_open_captures(self, meeting_id: str, organization_id: str) -> list[dict]:
        with closing(self.connect()) as db:
            rows = db.execute("""SELECT id,state,next_sequence,received_bytes,error_code,created_at
                FROM capture_sessions WHERE meeting_id=? AND organization_id=? AND state!='sealed'
                ORDER BY created_at,id""", (meeting_id, organization_id)).fetchall()
            return [dict(row) for row in rows]

    def save_capture_preview_window(self, session_id: str, organization_id: str, actor_id: str,
                                    start_ms: int, ownership_end_ms: int, asr_config_sha256: str,
                                    segments: list[dict], metrics: dict) -> None:
        with self.transaction() as db:
            capture = db.execute("""SELECT c.state,g.permission FROM capture_sessions c JOIN meeting_grants g
                ON g.meeting_id=c.meeting_id AND g.organization_id=c.organization_id
                WHERE c.id=? AND c.organization_id=? AND g.user_id=?""",
                (session_id, organization_id, actor_id)).fetchone()
            if not capture or capture["permission"] not in {"owner", "editor"}:
                raise LookupError("Capture not found")
            if capture["state"] != "capturing":
                raise ValueError("Capture is no longer accepting preview windows")
            db.execute("""INSERT INTO capture_preview_windows
                (session_id,start_ms,ownership_end_ms,asr_config_sha256,segments_json,wall_seconds,
                 peak_gpu_memory_mib,created_at) VALUES(?,?,?,?,?,?,?,?)
                ON CONFLICT(session_id,start_ms) DO UPDATE SET
                ownership_end_ms=excluded.ownership_end_ms,asr_config_sha256=excluded.asr_config_sha256,
                segments_json=excluded.segments_json,wall_seconds=excluded.wall_seconds,
                peak_gpu_memory_mib=excluded.peak_gpu_memory_mib,created_at=excluded.created_at""",
                (session_id, start_ms, ownership_end_ms, asr_config_sha256,
                 json.dumps(segments, ensure_ascii=False, separators=(",", ":")),
                 float(metrics.get("wallSeconds", 0)), metrics.get("peakGpuMemoryMiBObserved"), timestamp()))

    def get_capture_preview_windows(self, asset_id: str, organization_id: str,
                                    asr_config_sha256: str) -> list[dict]:
        with closing(self.connect()) as db:
            rows = db.execute("""SELECT w.* FROM capture_preview_windows w
                JOIN capture_sessions c ON c.id=w.session_id
                WHERE c.asset_id=? AND c.organization_id=? AND c.state='sealed' AND w.asr_config_sha256=?
                ORDER BY w.start_ms""", (asset_id, organization_id, asr_config_sha256)).fetchall()
            windows = []
            for row in rows:
                item = dict(row)
                item["segments"] = json.loads(item.pop("segments_json"))
                windows.append(item)
            return windows

    def delete_capture(self, session_id: str, organization_id: str, actor_id: str) -> bool:
        with self.transaction() as db:
            session = db.execute("""SELECT c.state,g.permission FROM capture_sessions c JOIN meeting_grants g
                ON g.meeting_id=c.meeting_id AND g.organization_id=c.organization_id
                WHERE c.id=? AND c.organization_id=? AND g.user_id=?""",
                (session_id, organization_id, actor_id)).fetchone()
            if not session or session["permission"] not in {"owner", "editor"} or session["state"] == "sealed":
                return False
            chunks = db.execute("SELECT storage_key FROM capture_chunks WHERE session_id=?", (session_id,)).fetchall()
            db.execute("DELETE FROM capture_sessions WHERE id=?", (session_id,))
        for chunk in chunks:
            self.resolve_key(chunk["storage_key"]).unlink(missing_ok=True)
        directory = (self.root / "captures" / session_id).resolve()
        if directory.is_relative_to(self.root):
            try:
                directory.rmdir()
            except OSError:
                pass
        return True

    def capture_chunk_path(self, session_id: str, sequence: int) -> Path:
        directory = (self.root / "captures" / session_id).resolve()
        if not directory.is_relative_to(self.root):
            raise ValueError("Capture path escapes data directory")
        directory.mkdir(parents=True, exist_ok=True)
        return directory / f"{sequence:06d}.chunk"

    def store_capture_chunk(self, session_id: str, organization_id: str, actor_id: str,
                            sequence: int, content: bytes) -> dict:
        if not content or len(content) > 32 * 1024 * 1024:
            raise ValueError("Capture chunk must be between 1 byte and 32 MiB")
        digest = hashlib.sha256(content).hexdigest()
        destination = self.capture_chunk_path(session_id, sequence)
        temporary = None
        moved = False
        try:
            with tempfile.NamedTemporaryFile(mode="wb", dir=destination.parent, prefix=".chunk-", suffix=".tmp", delete=False) as stream:
                temporary = Path(stream.name)
                stream.write(content)
                stream.flush()
                os.fsync(stream.fileno())
            with self.transaction() as db:
                session = db.execute("""SELECT c.*,g.permission FROM capture_sessions c JOIN meeting_grants g
                    ON g.meeting_id=c.meeting_id AND g.organization_id=c.organization_id
                    WHERE c.id=? AND c.organization_id=? AND g.user_id=?""",
                    (session_id, organization_id, actor_id)).fetchone()
                if not session or session["permission"] not in {"owner", "editor"}:
                    raise LookupError("Capture not found")
                previous = db.execute("SELECT sha256,size_bytes FROM capture_chunks WHERE session_id=? AND sequence=?",
                                      (session_id, sequence)).fetchone()
                if sequence < session["next_sequence"]:
                    if previous and previous["sha256"] == digest and previous["size_bytes"] == len(content):
                        return {"idempotent": True, "nextSequence": session["next_sequence"],
                                "receivedBytes": session["received_bytes"]}
                    raise ValueError("Capture sequence was already stored with different bytes")
                if session["state"] != "capturing":
                    raise ValueError("Capture session is not accepting chunks")
                if sequence != session["next_sequence"]:
                    raise ValueError("Capture chunks must arrive in sequence")
                if session["received_bytes"] + len(content) > MAX_CAPTURE_BYTES:
                    raise OverflowError("Capture exceeds the 2 GiB limit")
                os.replace(temporary, destination)
                temporary = None
                moved = True
                db.execute("""INSERT INTO capture_chunks(session_id,sequence,storage_key,size_bytes,sha256,created_at)
                    VALUES(?,?,?,?,?,?)""", (session_id, sequence, self.relative_key(destination), len(content), digest, timestamp()))
                received = session["received_bytes"] + len(content)
                next_sequence = sequence + 1
                db.execute("UPDATE capture_sessions SET next_sequence=?,received_bytes=?,updated_at=? WHERE id=?",
                           (next_sequence, received, timestamp(), session_id))
            return {"idempotent": False, "nextSequence": next_sequence, "receivedBytes": received}
        finally:
            if temporary:
                temporary.unlink(missing_ok=True)
            if moved:
                with closing(self.connect()) as db:
                    stored = db.execute("SELECT 1 FROM capture_chunks WHERE session_id=? AND sequence=?",
                                        (session_id, sequence)).fetchone()
                if not stored:
                    destination.unlink(missing_ok=True)

    def begin_capture_seal(self, session_id: str, organization_id: str, actor_id: str,
                           expected_sequence_count: int) -> dict:
        with self.transaction() as db:
            row = db.execute("""SELECT c.*,g.permission FROM capture_sessions c JOIN meeting_grants g
                ON g.meeting_id=c.meeting_id AND g.organization_id=c.organization_id
                WHERE c.id=? AND c.organization_id=? AND g.user_id=?""",
                (session_id, organization_id, actor_id)).fetchone()
            if not row or row["permission"] not in {"owner", "editor"}:
                raise LookupError("Capture not found")
            if row["state"] == "sealed":
                asset = db.execute("SELECT * FROM assets WHERE id=? AND organization_id=?",
                                   (row["asset_id"], organization_id)).fetchone()
                return {"state": "sealed", "asset": dict(asset) if asset else None}
            if expected_sequence_count < 1 or expected_sequence_count != row["next_sequence"]:
                raise ValueError("Capture is incomplete; one or more chunks are missing")
            chunks = db.execute("SELECT * FROM capture_chunks WHERE session_id=? ORDER BY sequence",
                                (session_id,)).fetchall()
            if len(chunks) != expected_sequence_count or any(chunk["sequence"] != index for index, chunk in enumerate(chunks)):
                raise ValueError("Capture chunk sequence is incomplete")
            db.execute("UPDATE capture_sessions SET state='sealing',error_code=NULL,updated_at=? WHERE id=?",
                       (timestamp(), session_id))
            result = dict(row)
            result["chunks"] = [dict(chunk) for chunk in chunks]
            return result

    def fail_capture(self, session_id: str, error_code: str) -> None:
        with self.transaction() as db:
            db.execute("UPDATE capture_sessions SET state='failed',error_code=?,updated_at=? WHERE id=? AND state!='sealed'",
                       (error_code, timestamp(), session_id))

    def complete_capture(self, session_id: str, organization_id: str, actor_id: str, details: dict) -> dict:
        session = self.get_capture_session(session_id, organization_id)
        if not session:
            raise LookupError("Capture not found")
        destination_keys = [chunk["storage_key"] for chunk in session["chunks"]]
        row = {"id": session["asset_id"], "organization_id": organization_id, "meeting_id": session["meeting_id"],
               "source_key": details["source_key"], "source_sha256": details["source_sha256"],
               "decoded_key": details["decoded_key"], "duration_ms": details["duration_ms"],
               "source_offset_ms": details["source_offset_ms"], "size_bytes": details["size_bytes"],
               "media_type": details["media_type"], "audio_track_index": details["audio_track_index"],
               "channels": details.get("channels"), "sample_rate_hz": details.get("sample_rate_hz"),
               "created_at": timestamp(), "kind": "audio", "decode_warning": details.get("decode_warning")}
        with self.transaction() as db:
            current = db.execute("""SELECT c.state,g.permission FROM capture_sessions c JOIN meeting_grants g
                ON g.meeting_id=c.meeting_id AND g.organization_id=c.organization_id
                WHERE c.id=? AND c.organization_id=? AND g.user_id=?""",
                (session_id, organization_id, actor_id)).fetchone()
            if not current or current["permission"] not in {"owner", "editor"}:
                raise LookupError("Capture not found")
            if current["state"] == "sealed":
                asset = db.execute("SELECT * FROM assets WHERE id=?", (session["asset_id"],)).fetchone()
                return dict(asset)
            if current["state"] != "sealing":
                raise ValueError("Capture is not ready to seal")
            db.execute("""INSERT INTO assets
                (id,organization_id,meeting_id,source_key,source_sha256,decoded_key,duration_ms,
                 source_offset_ms,size_bytes,media_type,audio_track_index,channels,sample_rate_hz,created_at,kind,decode_warning)
                VALUES (:id,:organization_id,:meeting_id,:source_key,:source_sha256,:decoded_key,
                 :duration_ms,:source_offset_ms,:size_bytes,:media_type,:audio_track_index,
                 :channels,:sample_rate_hz,:created_at,:kind,:decode_warning)""", row)
            db.execute("UPDATE capture_sessions SET state='sealed',asset_id=?,error_code=NULL,updated_at=? WHERE id=?",
                       (row["id"], timestamp(), session_id))
            db.execute("DELETE FROM capture_chunks WHERE session_id=?", (session_id,))
        for key in destination_keys:
            self.resolve_key(key).unlink(missing_ok=True)
        try:
            self.capture_chunk_path(session_id, 0).parent.rmdir()
        except OSError:
            pass
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
                AND (state IN ('queued','running') OR (state='ready' AND model_config_json=? AND EXISTS (
                    SELECT 1 FROM decision_results d WHERE d.job_id=jobs.id
                      AND d.transcript_revision=(SELECT transcript_revision FROM meetings WHERE id=jobs.meeting_id))))
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

    def latest_job_for_meeting(self, meeting_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("""SELECT id,state,stage,error_code FROM jobs
                WHERE meeting_id=? AND organization_id=? ORDER BY created_at DESC,id DESC LIMIT 1""",
                (meeting_id, organization_id)).fetchone()
            if not row:
                return None
            return {"id": row["id"], "state": row["state"], "stage": row["stage"],
                    "errorCode": row["error_code"]}

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

    def set_job_stage(self, job_id: str, worker_id: str, stage: str) -> bool:
        if stage not in {"transcribe", "extract", "validate", "render", "complete"}:
            raise ValueError("Unsupported job stage")
        with self.transaction() as db:
            result = db.execute("UPDATE jobs SET stage=?,updated_at=? WHERE id=? AND state='running' AND lease_owner=?",
                                (stage, timestamp(), job_id, worker_id))
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
                segment_id = segment["id"]
                conflict = db.execute("SELECT job_id FROM segments WHERE id=?", (segment_id,)).fetchone()
                if conflict and conflict["job_id"] != job["id"]:
                    original_id = segment_id
                    suffix = 0
                    while conflict:
                        source = f"notavra-segment:{job['id']}:{original_id}:{suffix}"
                        segment_id = str(uuid.uuid5(uuid.NAMESPACE_URL, source))
                        conflict = db.execute("SELECT job_id FROM segments WHERE id=?", (segment_id,)).fetchone()
                        suffix += 1
                db.execute("""INSERT INTO segments VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (segment_id, job["organization_id"], job["meeting_id"], job["asset_id"], job["id"],
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

    def revise_segment(self, meeting_id: str, organization_id: str, segment_id: str,
                       editor_id: str, transcript_revision: int, text: str) -> dict | None:
        rows = self.revise_segments(meeting_id, organization_id, editor_id, transcript_revision,
                                    [{"segmentId": segment_id, "text": text}])
        return rows[0] if rows else None

    def revise_segments(self, meeting_id: str, organization_id: str, editor_id: str,
                        transcript_revision: int, corrections: list[dict]) -> list[dict] | None:
        cleaned = []
        seen = set()
        for correction in corrections:
            segment_id, text = correction["segmentId"], correction["text"].strip()
            if not text or len(text) > 5000:
                raise ValueError("Transcript text must be 1–5000 characters")
            if segment_id in seen:
                raise ValueError("A transcript passage can be corrected only once per batch")
            seen.add(segment_id)
            cleaned.append((segment_id, text))
        with self.transaction() as db:
            meeting = db.execute("SELECT transcript_revision FROM meetings WHERE id=? AND organization_id=?",
                                 (meeting_id, organization_id)).fetchone()
            if not meeting or meeting["transcript_revision"] != transcript_revision:
                return None
            segments = []
            for segment_id, text in cleaned:
                segment = db.execute("""SELECT * FROM segments WHERE id=? AND meeting_id=? AND organization_id=?
                    AND transcript_revision=?""", (segment_id, meeting_id, organization_id, transcript_revision)).fetchone()
                if not segment:
                    return None
                segments.append((segment, text))
            if not segments:
                return None
            next_revision = transcript_revision + 1
            db.execute("UPDATE segments SET transcript_revision=? WHERE meeting_id=? AND transcript_revision=?",
                       (next_revision, meeting_id, transcript_revision))
            for segment, text in segments:
                db.execute("""INSERT INTO segment_revisions(id,organization_id,meeting_id,segment_id,editor_id,
                    from_revision,to_revision,old_text,new_text,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), organization_id, meeting_id, segment["id"], editor_id, transcript_revision,
                     next_revision, segment["text"], text, timestamp()))
                db.execute("UPDATE segments SET text=? WHERE id=?", (text, segment["id"]))
            db.execute("UPDATE meetings SET transcript_revision=?,status='transcript_review',updated_at=? WHERE id=?",
                       (next_revision, timestamp(), meeting_id))
            db.execute("UPDATE artifacts SET status='superseded' WHERE meeting_id=? AND status='ready'",
                       (meeting_id,))
            rows = db.execute("SELECT * FROM segments WHERE meeting_id=? AND transcript_revision=? ORDER BY start_ms,id",
                              (meeting_id, next_revision)).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["words"] = json.loads(item.pop("words_json"))
                result.append(item)
            return result

    def undo_transcript_revision(self, meeting_id: str, organization_id: str, editor_id: str,
                                 transcript_revision: int) -> list[dict] | None:
        with self.transaction() as db:
            meeting = db.execute("SELECT transcript_revision FROM meetings WHERE id=? AND organization_id=?",
                                 (meeting_id, organization_id)).fetchone()
            if not meeting or meeting["transcript_revision"] != transcript_revision:
                return None
            revisions = db.execute("""SELECT r.* FROM segment_revisions r
                WHERE r.meeting_id=? AND r.organization_id=? AND r.to_revision=? ORDER BY r.created_at,r.id""",
                (meeting_id, organization_id, transcript_revision)).fetchall()
            if not revisions:
                return None
            next_revision = transcript_revision + 1
            for revision in revisions:
                segment = db.execute("SELECT * FROM segments WHERE id=? AND meeting_id=? AND transcript_revision=?",
                                     (revision["segment_id"], meeting_id, transcript_revision)).fetchone()
                if not segment or segment["text"] != revision["new_text"]:
                    return None
            for revision in revisions:
                segment = db.execute("SELECT text FROM segments WHERE id=?", (revision["segment_id"],)).fetchone()
                db.execute("""INSERT INTO segment_revisions(id,organization_id,meeting_id,segment_id,editor_id,
                    from_revision,to_revision,old_text,new_text,created_at) VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), organization_id, meeting_id, revision["segment_id"], editor_id,
                     transcript_revision, next_revision, segment["text"], revision["old_text"], timestamp()))
                db.execute("UPDATE segments SET text=? WHERE id=?", (revision["old_text"], revision["segment_id"]))
            db.execute("UPDATE segments SET transcript_revision=? WHERE meeting_id=? AND transcript_revision=?",
                       (next_revision, meeting_id, transcript_revision))
            db.execute("UPDATE meetings SET transcript_revision=?,status='transcript_review',updated_at=? WHERE id=?",
                       (next_revision, timestamp(), meeting_id))
            db.execute("UPDATE artifacts SET status='superseded' WHERE meeting_id=? AND status='ready'", (meeting_id,))
            rows = db.execute("SELECT * FROM segments WHERE meeting_id=? AND transcript_revision=? ORDER BY start_ms,id",
                              (meeting_id, next_revision)).fetchall()
            result = []
            for row in rows:
                item = dict(row)
                item["words"] = json.loads(item.pop("words_json"))
                result.append(item)
            return result

    def can_undo_transcript_revision(self, meeting_id: str, organization_id: str,
                                     transcript_revision: int) -> bool:
        with closing(self.connect()) as db:
            return db.execute("""SELECT 1 FROM segment_revisions
                WHERE meeting_id=? AND organization_id=? AND to_revision=? LIMIT 1""",
                (meeting_id, organization_id, transcript_revision)).fetchone() is not None

    def save_decisions(self, job: dict, worker_id: str, result: dict) -> None:
        with self.transaction() as db:
            lease = db.execute("SELECT lease_owner,state FROM jobs WHERE id=?", (job["id"],)).fetchone()
            meeting = db.execute("SELECT transcript_revision FROM meetings WHERE id=? AND organization_id=?",
                                 (job["meeting_id"], job["organization_id"])).fetchone()
            if not lease or lease["lease_owner"] != worker_id or lease["state"] != "running":
                raise RuntimeError("Job lease lost before decision commit")
            if not meeting or result.get("transcriptRevision") != meeting["transcript_revision"]:
                raise RuntimeError("Decision result does not match the current transcript revision")
            db.execute("""INSERT INTO decision_results(job_id,organization_id,meeting_id,transcript_revision,result_json,created_at)
                VALUES(?,?,?,?,?,?) ON CONFLICT(job_id) DO UPDATE SET transcript_revision=excluded.transcript_revision,
                result_json=excluded.result_json,created_at=excluded.created_at""",
                (job["id"], job["organization_id"], job["meeting_id"], result["transcriptRevision"],
                 json.dumps(result, ensure_ascii=False, separators=(",", ":")), timestamp()))

    def get_job_decisions(self, job_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("SELECT result_json FROM decision_results WHERE job_id=? AND organization_id=?",
                             (job_id, organization_id)).fetchone()
            return json.loads(row["result_json"]) if row else None

    def get_meeting_decisions(self, meeting_id: str, organization_id: str) -> dict | None:
        with closing(self.connect()) as db:
            row = db.execute("""SELECT d.result_json FROM decision_results d JOIN meetings m ON m.id=d.meeting_id
                JOIN jobs j ON j.id=d.job_id AND j.state='ready'
                WHERE d.meeting_id=? AND d.organization_id=? AND d.transcript_revision=m.transcript_revision
                ORDER BY d.created_at DESC,d.job_id DESC LIMIT 1""", (meeting_id, organization_id)).fetchone()
            return json.loads(row["result_json"]) if row else None
