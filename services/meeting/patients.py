"""Small patient directory; meeting links never grant meeting access."""

import base64
import json
import sqlite3
import unicodedata
import uuid
from contextlib import closing

from .storage import Storage, timestamp


def search_key(value: str) -> str:
    return unicodedata.normalize("NFKC", value).casefold().strip()


def _like(value: str) -> str:
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _access_sql(alias: str = "p") -> str:
    return f"""({alias}.created_by=? OR EXISTS (
        SELECT 1 FROM patient_meetings pm JOIN meeting_grants mg
          ON mg.meeting_id=pm.meeting_id AND mg.organization_id=pm.organization_id
        WHERE pm.patient_id={alias}.id AND pm.organization_id={alias}.organization_id
          AND mg.user_id=? AND mg.organization_id=?))"""


def _access_params(actor: dict) -> tuple[str, str, str]:
    return actor["id"], actor["id"], actor["organization_id"]


class PatientDirectory:
    def __init__(self, store: Storage):
        self.store = store

    def create(self, actor: dict, name: str, reference: str | None, status: str) -> dict:
        name, reference = name.strip(), reference.strip() if reference else None
        if not name or len(name) > 160 or (reference and len(reference) > 120):
            raise ValueError("Patient name or hospital reference is invalid")
        now, patient_id = timestamp(), str(uuid.uuid4())
        with self.store.transaction() as db:
            db.execute("""INSERT INTO patients
                (id,organization_id,display_name,search_name,hospital_reference,search_reference,status,created_by,created_at,updated_at)
                VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (patient_id, actor["organization_id"], name, search_key(name), reference,
                 search_key(reference or ""), status, actor["id"], now, now))
        return self.get(actor, patient_id)

    def list(self, actor: dict, *, query: str = "", limit: int = 25, cursor: str | None = None) -> dict:
        key = search_key(query)
        where = f"p.organization_id=? AND {_access_sql()}"
        params: list = [actor["organization_id"], *_access_params(actor)]
        if key:
            where += " AND (p.search_name LIKE ? ESCAPE '\\' OR p.search_reference LIKE ? ESCAPE '\\')"
            params.extend((_like(key), _like(key)))
        after = None
        if cursor:
            try:
                raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4))
                data = json.loads(raw)
                if data.get("q") != key:
                    raise ValueError
                after = (data["name"], data["id"])
            except (ValueError, TypeError, KeyError, json.JSONDecodeError) as exc:
                raise ValueError("Invalid patient pagination cursor") from exc
        with closing(self.store.connect()) as db:
            total = db.execute(f"SELECT COUNT(*) FROM patients p WHERE {where}", params).fetchone()[0]
            page_where, page_params = where, list(params)
            if after:
                page_where += " AND (p.search_name,p.id)>(?,?)"
                page_params.extend(after)
            rows = db.execute(f"""SELECT p.* FROM patients p WHERE {page_where}
                ORDER BY p.search_name,p.id LIMIT ?""", (*page_params, limit + 1)).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        next_cursor = None
        if has_more and rows:
            encoded = json.dumps({"q": key, "name": rows[-1]["search_name"], "id": rows[-1]["id"]},
                                 separators=(",", ":")).encode()
            next_cursor = base64.urlsafe_b64encode(encoded).decode().rstrip("=")
        return {"patients": [self._record(row) for row in rows], "total": total,
                "limit": limit, "nextCursor": next_cursor, "hasMore": has_more}

    def get(self, actor: dict, patient_id: str) -> dict | None:
        with closing(self.store.connect()) as db:
            row = db.execute(f"""SELECT p.* FROM patients p WHERE p.id=? AND p.organization_id=?
                AND {_access_sql()}""", (patient_id, actor["organization_id"], *_access_params(actor))).fetchone()
            if not row:
                return None
            result = self._record(row)
            result["canDelete"] = row["created_by"] == actor["id"] or actor["role"] == "administrator"
            result["linkedMeetingCount"] = db.execute(
                "SELECT COUNT(*) FROM patient_meetings WHERE patient_id=? AND organization_id=?",
                (patient_id, actor["organization_id"])).fetchone()[0]
            refs = db.execute("""SELECT m.id,m.title,m.recorded_at,m.status FROM patient_meetings pm
                JOIN meetings m ON m.id=pm.meeting_id AND m.organization_id=pm.organization_id
                JOIN meeting_grants mg ON mg.meeting_id=m.id AND mg.organization_id=m.organization_id
                WHERE pm.patient_id=? AND pm.organization_id=? AND mg.user_id=?
                ORDER BY m.recorded_at DESC,m.id""",
                (patient_id, actor["organization_id"], actor["id"])).fetchall()
            result["meetings"] = [{"id": ref["id"], "title": ref["title"],
                                   "recordedAt": ref["recorded_at"], "status": ref["status"]} for ref in refs]
            return result

    def update(self, actor: dict, patient_id: str, changes: dict) -> dict | None:
        if not changes:
            raise ValueError("At least one patient field must be changed")
        allowed = {"display_name", "hospital_reference", "status"}
        if set(changes) - allowed:
            raise ValueError("Unsupported patient field")
        if any(value is None and key != "hospital_reference" for key, value in changes.items()):
            raise ValueError("Patient name and status cannot be cleared")
        if "display_name" in changes:
            changes["display_name"] = changes["display_name"].strip()
            if not changes["display_name"] or len(changes["display_name"]) > 160:
                raise ValueError("Patient name is invalid")
            changes["search_name"] = search_key(changes["display_name"])
        if "hospital_reference" in changes:
            value = changes["hospital_reference"]
            changes["hospital_reference"] = value.strip() if value else None
            if changes["hospital_reference"] and len(changes["hospital_reference"]) > 120:
                raise ValueError("Hospital reference is too long")
            changes["search_reference"] = search_key(changes["hospital_reference"] or "")
        assignments = ",".join(f"{column}=?" for column in changes)
        with self.store.transaction() as db:
            result = db.execute(f"""UPDATE patients SET {assignments},updated_at=? WHERE id=? AND organization_id=?
                AND {_access_sql('patients')} AND (created_by=? OR EXISTS (
                    SELECT 1 FROM patient_meetings pm JOIN meeting_grants mg
                      ON mg.meeting_id=pm.meeting_id AND mg.organization_id=pm.organization_id
                    WHERE pm.patient_id=patients.id AND pm.organization_id=patients.organization_id
                      AND mg.user_id=? AND mg.organization_id=? AND mg.permission IN ('owner','editor')))""",
                (*changes.values(), timestamp(), patient_id, actor["organization_id"], *_access_params(actor),
                 actor["id"], actor["id"], actor["organization_id"]))
            if result.rowcount != 1:
                return None
        return self.get(actor, patient_id)

    def delete(self, actor: dict, patient_id: str) -> dict | None:
        with self.store.transaction() as db:
            patient = db.execute("""SELECT id FROM patients WHERE id=? AND organization_id=?
                AND (created_by=? OR ?)""",
                (patient_id, actor["organization_id"], actor["id"], actor["role"] == "administrator")).fetchone()
            if not patient:
                return None
            meeting_count = db.execute("SELECT COUNT(*) FROM patient_meetings WHERE patient_id=? AND organization_id=?",
                                       (patient_id, actor["organization_id"])).fetchone()[0]
            db.execute("DELETE FROM patient_meetings WHERE patient_id=? AND organization_id=?",
                       (patient_id, actor["organization_id"]))
            db.execute("DELETE FROM patients WHERE id=? AND organization_id=?",
                       (patient_id, actor["organization_id"]))
            db.execute("""INSERT INTO deletion_audit
                (id,organization_id,actor_id,subject_type,subject_id,action,created_at,transcript_revision)
                VALUES(?,?,?,?,?,?,?,NULL)""",
                (str(uuid.uuid4()), actor["organization_id"], actor["id"], "patient", patient_id,
                 "patient_identity_purged", timestamp()))
            return {"linkedMeetingCount": meeting_count}

    def link_meeting(self, actor: dict, patient_id: str, meeting_id: str, *, linked: bool) -> bool:
        with self.store.transaction() as db:
            meeting_permission = db.execute("""SELECT permission FROM meeting_grants WHERE meeting_id=?
                AND organization_id=? AND user_id=?""",
                (meeting_id, actor["organization_id"], actor["id"])).fetchone()
            patient = db.execute(f"""SELECT p.id FROM patients p WHERE p.id=? AND p.organization_id=?
                AND {_access_sql()}""", (patient_id, actor["organization_id"], *_access_params(actor))).fetchone()
            if not patient or not meeting_permission or meeting_permission["permission"] not in {"owner", "editor"}:
                return False
            if linked:
                db.execute("""INSERT OR IGNORE INTO patient_meetings
                    (patient_id,meeting_id,organization_id,linked_by,created_at) VALUES(?,?,?,?,?)""",
                    (patient_id, meeting_id, actor["organization_id"], actor["id"], timestamp()))
                return True
            db.execute("DELETE FROM patient_meetings WHERE patient_id=? AND meeting_id=? AND organization_id=?",
                       (patient_id, meeting_id, actor["organization_id"]))
            return True

    @staticmethod
    def _record(row: sqlite3.Row) -> dict:
        return {"id": row["id"], "displayName": row["display_name"],
                "hospitalReference": row["hospital_reference"], "status": row["status"],
                "createdAt": row["created_at"], "updatedAt": row["updated_at"]}
