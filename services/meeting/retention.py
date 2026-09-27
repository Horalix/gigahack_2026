"""Best-effort local expiry for configured meeting data categories."""

from datetime import datetime, timedelta, timezone
import uuid

from .storage import Storage, timestamp


def _cutoff(days: int) -> str:
    return timestamp((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())


def apply_expirations(store: Storage) -> int:
    """Expire opted-in categories. `None` in the policy means manual deletion only."""
    now = timestamp()
    cleaned = 0
    with store.transaction() as db:
        policy = db.execute("SELECT * FROM retention_policy WHERE singleton=1").fetchone()
        if not policy:
            return 0
        organization_id = policy["organization_id"]

        audio_days = policy["audio_days"]
        if audio_days is not None:
            rows = db.execute("""SELECT a.id,a.meeting_id,a.source_key,a.decoded_key,m.transcript_revision
                FROM assets a JOIN meetings m ON m.id=a.meeting_id
                WHERE a.organization_id=? AND m.legal_hold=0 AND a.source_purged_at IS NULL AND a.created_at<=?
                  AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.asset_id=a.id AND j.state='running')""",
                (organization_id, _cutoff(audio_days))).fetchall()
            for asset in rows:
                keys = {asset["source_key"], asset["decoded_key"]}
                capture_rows = db.execute("SELECT id FROM capture_sessions WHERE asset_id=?", (asset["id"],)).fetchall()
                for capture in capture_rows:
                    keys.update(row["storage_key"] for row in db.execute(
                        "SELECT storage_key FROM capture_chunks WHERE session_id=?", (capture["id"],)))
                    db.execute("DELETE FROM capture_sessions WHERE id=?", (capture["id"],))
                for key in keys:
                    db.execute("INSERT OR IGNORE INTO file_cleanup(storage_key,queued_at) VALUES(?,?)", (key, now))
                db.execute("UPDATE jobs SET state='cancelled',stage='cancelled',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE asset_id=? AND state='queued'",
                           (now, asset["id"]))
                db.execute("UPDATE assets SET source_purged_at=? WHERE id=?", (now, asset["id"]))
                db.execute("""INSERT INTO deletion_audit
                    (id,organization_id,actor_id,subject_type,subject_id,action,created_at,transcript_revision)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), organization_id, "system:retention", "audio", asset["id"],
                     "retention_expired", now, asset["transcript_revision"]))
                cleaned += len(keys)

        transcript_days = policy["transcript_days"]
        if transcript_days is not None:
            rows = db.execute("""SELECT m.id,m.transcript_revision,MIN(s.created_at) AS first_transcript_at
                FROM meetings m JOIN segments s ON s.meeting_id=m.id AND s.organization_id=m.organization_id
                WHERE m.organization_id=? AND m.legal_hold=0 AND m.transcript_purged_at IS NULL
                  AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.meeting_id=m.id AND j.state='running')
                GROUP BY m.id HAVING first_transcript_at<=?""",
                (organization_id, _cutoff(transcript_days))).fetchall()
            for meeting in rows:
                db.execute("UPDATE jobs SET state='cancelled',stage='cancelled',lease_owner=NULL,lease_until=NULL,updated_at=? WHERE meeting_id=? AND state='queued'",
                           (now, meeting["id"]))
                job_ids = [row["id"] for row in db.execute("SELECT id FROM jobs WHERE meeting_id=?", (meeting["id"],))]
                checkpoint_keys = []
                for job_id in job_ids:
                    checkpoint = store.assets_dir / meeting["id"] / f"{job_id}.transcript.json"
                    if checkpoint.is_file():
                        checkpoint_keys.append(store.relative_key(checkpoint))
                artifact_keys = [row["storage_key"] for row in db.execute(
                    "SELECT storage_key FROM artifacts WHERE meeting_id=? AND organization_id=?",
                    (meeting["id"], organization_id))]
                db.execute("DELETE FROM capture_preview_windows WHERE session_id IN (SELECT id FROM capture_sessions WHERE meeting_id=?)",
                           (meeting["id"],))
                db.execute("DELETE FROM segment_revisions WHERE meeting_id=?", (meeting["id"],))
                db.execute("DELETE FROM segments WHERE meeting_id=?", (meeting["id"],))
                db.execute("DELETE FROM decision_results WHERE meeting_id=?", (meeting["id"],))
                db.execute("DELETE FROM artifacts WHERE meeting_id=?", (meeting["id"],))
                db.execute("UPDATE meetings SET transcript_purged_at=?,status='retention_expired',updated_at=? WHERE id=?",
                           (now, now, meeting["id"]))
                for key in [*artifact_keys, *checkpoint_keys]:
                    db.execute("INSERT OR IGNORE INTO file_cleanup(storage_key,queued_at) VALUES(?,?)", (key, now))
                db.execute("""INSERT INTO deletion_audit
                    (id,organization_id,actor_id,subject_type,subject_id,action,created_at,transcript_revision)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), organization_id, "system:retention", "transcript", meeting["id"],
                     "retention_expired", now, meeting["transcript_revision"]))
                cleaned += len(artifact_keys) + len(checkpoint_keys)

        artifact_days = policy["artifact_days"]
        if artifact_days is not None:
            rows = db.execute("""SELECT a.id,a.meeting_id,a.storage_key,a.transcript_revision FROM artifacts a
                JOIN meetings m ON m.id=a.meeting_id WHERE a.organization_id=? AND m.legal_hold=0
                  AND a.approved_at<=?""",
                (organization_id, _cutoff(artifact_days))).fetchall()
            for artifact in rows:
                db.execute("DELETE FROM artifacts WHERE id=?", (artifact["id"],))
                db.execute("INSERT OR IGNORE INTO file_cleanup(storage_key,queued_at) VALUES(?,?)",
                           (artifact["storage_key"], now))
                db.execute("""INSERT INTO deletion_audit
                    (id,organization_id,actor_id,subject_type,subject_id,action,created_at,transcript_revision)
                    VALUES(?,?,?,?,?,?,?,?)""",
                    (str(uuid.uuid4()), organization_id, "system:retention", "artifact", artifact["id"],
                     "retention_expired", now, artifact["transcript_revision"]))
                cleaned += 1

    store.flush_file_cleanup()
    return cleaned
