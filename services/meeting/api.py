"""Loopback HTTP API for durable local meeting ingest and job status."""

import asyncio
import hashlib
import ipaddress
import json
import os
import subprocess
import uuid
import wave
import io
from pathlib import Path

from fastapi import Cookie, Depends, FastAPI, File, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from .auth import AuthService, SESSION_COOKIE, SESSION_SECONDS
from .contracts import CreateAccount, CreateCapture, CreateJob, CreateMeeting, CreatePatient, ErrorEnvelope, FinalizeArtifact, GrantMeetingAccess, LoginRequest, ReviseSegment, ReviseSegments, SealCapture, SetAccountActive, SetupRequest, UndoTranscriptRevision, UpdatePatient
from .capture import CaptureError, seal_capture
from .inference_lock import InferenceBusy, inference_device_lock
from .media import MAX_UPLOAD_BYTES, MediaError, decode
from .patients import PatientDirectory
from .storage import Storage, timestamp


DEFAULT_ALLOWED_ORIGINS = {
    "http://localhost:1420", "http://127.0.0.1:1420", "tauri://localhost",
    "http://tauri.localhost", "https://tauri.localhost",
}


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None, retryable: bool = False):
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable


def meeting_record(row: dict, patient_link_ids: list[str] | None = None) -> dict:
    return {"id": row["id"], "organizationId": row["organization_id"],
            "title": row["title"], "recordedAt": row["recorded_at"], "timeZone": row["time_zone"],
            "meetingType": row["meeting_type"], "suggestedMeetingType": None,
            "outputLanguage": row["output_language"], "patientLinkIds": patient_link_ids or [], "participantIds": [],
            "status": row["status"], "transcriptRevision": row["transcript_revision"],
            "createdAt": row["created_at"], "updatedAt": row["updated_at"]}


def asset_record(row: dict | None) -> dict | None:
    if row is None:
        return None
    return {"id": row["id"], "organizationId": row["organization_id"],
            "meetingId": row["meeting_id"], "kind": row["kind"], "storageKey": row["source_key"],
            "sha256": row["source_sha256"], "durationMs": row["duration_ms"],
            "sourceOffsetMs": row["source_offset_ms"], "sizeBytes": row["size_bytes"],
            "mediaType": row["media_type"], "audioTrackIndex": row["audio_track_index"],
            "channels": row["channels"], "sampleRateHz": row["sample_rate_hz"],
            "decodeWarning": row["decode_warning"],
            "createdAt": row["created_at"]}


def job_record(row: dict) -> dict:
    return {"id": row["id"], "organizationId": row["organization_id"],
            "meetingId": row["meeting_id"], "state": row["state"], "stage": row["stage"],
            "profileId": row["profile_id"], "modelConfig": json.loads(row["model_config_json"]),
            "errorCode": row["error_code"], "progressMs": row["progress_ms"],
            "attempts": row["attempts"], "artifactIds": [],
            "createdAt": row["created_at"], "updatedAt": row["updated_at"]}


def segment_record(row: dict) -> dict:
    return {"id": row["id"], "organizationId": row["organization_id"],
            "meetingId": row["meeting_id"], "assetId": row["asset_id"],
            "transcriptRevision": row["transcript_revision"], "startMs": row["start_ms"],
            "endMs": row["end_ms"], "text": row["text"], "language": row["language"],
            "speakerClusterId": None, "origin": row["origin"], "words": row["words"]}


def artifact_record(row: dict) -> dict:
    return {"id": row["id"], "organizationId": row["organization_id"],
            "meetingId": row["meeting_id"], "transcriptRevision": row["transcript_revision"],
            "storageKey": row["storage_key"], "mimeType": row["mime_type"],
            "sha256": row["sha256"], "status": row["status"],
            "approvedBy": row["approved_by"], "approvedAt": row["approved_at"],
            "createdAt": row["created_at"]}


def host_gpu_memory_gb() -> float | None:
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=2, check=True)
        values = [int(line.strip()) for line in result.stdout.decode().splitlines() if line.strip()]
        return max(values) / 1024 if values else None
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return None


def host_gpu_free_memory_gb() -> float | None:
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                timeout=2, check=True)
        values = [int(line.strip()) for line in result.stdout.decode().splitlines() if line.strip()]
        return values[0] / 1024 if values else None
    except (FileNotFoundError, subprocess.SubprocessError, ValueError):
        return None


def host_available_memory_gb() -> float | None:
    """Return available physical RAM without adding a runtime dependency."""
    if os.name == "nt":
        import ctypes

        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.ullAvailPhys / (1024 ** 3)
        return None
    meminfo = Path("/proc/meminfo")
    if meminfo.is_file():
        for line in meminfo.read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) / (1024 ** 2)
    return None


def create_app(data_root: Path | None = None) -> FastAPI:
    app = FastAPI(title="Secure MOM local meeting service", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.store = Storage(data_root)
    app.state.auth = AuthService(app.state.store)
    configured_origins = os.environ.get("MOM_ALLOWED_ORIGINS")
    allowed_origins = ({origin.strip() for origin in configured_origins.split(",") if origin.strip()}
                       if configured_origins else DEFAULT_ALLOWED_ORIGINS)
    app.state.allowed_origins = allowed_origins
    app.add_middleware(CORSMiddleware, allow_origins=sorted(allowed_origins), allow_credentials=True,
                       allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
                       allow_headers=["Content-Type"])

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
        client_host = request.client.host if request.client else ""
        try:
            local_client = ipaddress.ip_address(client_host).is_loopback
        except ValueError:
            local_client = client_host == "testclient"
        origin = request.headers.get("origin")
        if not local_client:
            return JSONResponse(status_code=403, content={"code": "LOOPBACK_ONLY", "message": "Service accepts local connections only", "requestId": request.state.request_id})
        if origin is not None and origin not in allowed_origins:
            return JSONResponse(status_code=403, content={"code": "ORIGIN_DENIED", "message": "Request origin is not allowed", "requestId": request.state.request_id})
        if request.method not in {"GET", "HEAD", "OPTIONS"} and origin not in allowed_origins:
            return JSONResponse(status_code=403, content={"code": "ORIGIN_REQUIRED", "message": "A trusted local origin is required", "requestId": request.state.request_id})
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["Cache-Control"] = "no-store"
        return response

    @app.exception_handler(ServiceError)
    async def service_error(request: Request, exc: ServiceError):
        body = ErrorEnvelope(code=exc.code, message=exc.message, retryable=exc.retryable,
                             requestId=request.state.request_id, details=exc.details)
        return JSONResponse(status_code=exc.status, content=body.model_dump())

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError):
        body = ErrorEnvelope(code="INVALID_REQUEST", message="The request is invalid.",
                             retryable=False, requestId=request.state.request_id)
        return JSONResponse(status_code=422, content=body.model_dump())

    def store(request: Request) -> Storage:
        return request.app.state.store

    def principal(request: Request, token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
        user = request.app.state.auth.authenticate_session(token)
        if not user:
            raise ServiceError(401, "AUTH_REQUIRED", "Sign in to use this service")
        return user

    def administrator(actor: dict = Depends(principal)) -> dict:
        if actor["role"] != "administrator":
            raise ServiceError(403, "ROLE_REQUIRED", "Administrator role is required")
        return actor

    def meeting_or_404(meeting_id: str, actor: dict, db: Storage, *, write: bool = False) -> dict:
        meeting = db.get_meeting(meeting_id, actor["organization_id"])
        permission = db.meeting_permission(meeting_id, actor["id"], actor["organization_id"]) if meeting else None
        if not meeting or not permission:
            raise ServiceError(404, "MEETING_NOT_FOUND", "Meeting not found")
        if write and permission not in {"owner", "editor"}:
            raise ServiceError(403, "MEETING_READ_ONLY", "This account has read-only access")
        return meeting

    @app.post("/api/auth/login")
    def login(data: LoginRequest, request: Request, response: Response):
        host = request.client.host if request.client else "127.0.0.1"
        result = request.app.state.auth.authenticate_password(data.username, data.password, host)
        if not result:
            raise ServiceError(401, "INVALID_CREDENTIALS", "Username or password is incorrect")
        token, user = result
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_SECONDS, path="/",
                            httponly=True, secure=request.url.scheme == "https", samesite="strict")
        return {"user": user}

    @app.post("/api/auth/setup", status_code=201)
    def initial_setup(data: SetupRequest, request: Request, response: Response, db: Storage = Depends(store)):
        if db.user_count():
            raise ServiceError(409, "SETUP_COMPLETE", "An administrator account already exists")
        try:
            request.app.state.auth.create_user(db.installation_organization(), data.username,
                                               data.password, "administrator", bootstrap=True)
        except ValueError as exc:
            raise ServiceError(422, "SETUP_INVALID", str(exc)) from exc
        host = request.client.host if request.client else "127.0.0.1"
        token, user = request.app.state.auth.authenticate_password(data.username, data.password, host)
        if not token:
            raise ServiceError(500, "SETUP_LOGIN_FAILED", "The administrator account was created; sign in to continue")
        response.set_cookie(SESSION_COOKIE, token, max_age=SESSION_SECONDS, path="/",
                            httponly=True, secure=request.url.scheme == "https", samesite="strict")
        return {"user": user}

    @app.get("/api/auth/me")
    def current_user(actor: dict = Depends(principal)):
        return {"user": AuthService.public_user(actor)}

    @app.post("/api/auth/logout")
    def logout(request: Request, response: Response, token: str | None = Cookie(default=None, alias=SESSION_COOKIE)):
        request.app.state.auth.logout(token)
        response.delete_cookie(SESSION_COOKIE, path="/", httponly=True,
                               secure=request.url.scheme == "https", samesite="strict")
        return {"ok": True}

    @app.get("/api/users")
    def list_users(db: Storage = Depends(store), _actor: dict = Depends(administrator)):
        return {"users": [{"id": row["id"], "username": row["username"], "role": row["role"],
                           "active": bool(row["active"]), "createdAt": row["created_at"]} for row in db.list_users()]}

    @app.post("/api/users", status_code=201)
    def create_user(data: CreateAccount, request: Request, _actor: dict = Depends(administrator)):
        try:
            user = request.app.state.auth.create_user(
                request.app.state.store.installation_organization(), data.username, data.password, data.role)
        except ValueError as exc:
            raise ServiceError(409, "ACCOUNT_NOT_CREATED", str(exc)) from exc
        return {"user": AuthService.public_user(user)}

    @app.patch("/api/users/{user_id}")
    def set_user_active(user_id: str, data: SetAccountActive, db: Storage = Depends(store), _actor: dict = Depends(administrator)):
        if not db.set_user_active(user_id, data.active):
            raise ServiceError(404, "USER_NOT_FOUND", "Account not found")
        return {"id": user_id, "active": data.active}

    @app.get("/api/health")
    def health(db: Storage = Depends(store)):
        return {"status": "ok", "service": "meeting", "setupRequired": db.user_count() == 0}

    @app.get("/api/patients")
    def list_patients(q: str = Query(default="", max_length=120), limit: int = Query(default=25, ge=1, le=100),
                      cursor: str | None = Query(default=None, max_length=1024),
                      actor: dict = Depends(principal), db: Storage = Depends(store)):
        try:
            return PatientDirectory(db).list(actor, query=q, limit=limit, cursor=cursor)
        except ValueError as exc:
            raise ServiceError(422, "PATIENT_CURSOR_INVALID", str(exc)) from exc

    @app.post("/api/patients", status_code=201)
    def create_patient(data: CreatePatient, actor: dict = Depends(principal), db: Storage = Depends(store)):
        if actor["role"] == "reviewer":
            raise ServiceError(403, "ROLE_READ_ONLY", "Reviewer accounts cannot create patients")
        try:
            return {"patient": PatientDirectory(db).create(actor, data.displayName, data.hospitalReference, data.status)}
        except ValueError as exc:
            raise ServiceError(422, "PATIENT_INVALID", str(exc)) from exc

    @app.get("/api/patients/{patient_id}")
    def get_patient(patient_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        patient = PatientDirectory(db).get(actor, patient_id)
        if not patient:
            raise ServiceError(404, "PATIENT_NOT_FOUND", "Patient not found")
        return {"patient": patient}

    @app.patch("/api/patients/{patient_id}")
    def update_patient(patient_id: str, data: UpdatePatient, actor: dict = Depends(principal), db: Storage = Depends(store)):
        if actor["role"] == "reviewer":
            raise ServiceError(403, "ROLE_READ_ONLY", "Reviewer accounts cannot edit patients")
        names = {"displayName": "display_name", "hospitalReference": "hospital_reference", "status": "status"}
        changes = {names[key]: getattr(data, key) for key in data.model_fields_set}
        try:
            patient = PatientDirectory(db).update(actor, patient_id, changes)
        except (TypeError, ValueError) as exc:
            raise ServiceError(422, "PATIENT_INVALID", str(exc)) from exc
        if not patient:
            raise ServiceError(404, "PATIENT_NOT_FOUND", "Patient not found")
        return {"patient": patient}

    @app.post("/api/patients/{patient_id}/meetings/{meeting_id}", status_code=201)
    def link_patient_meeting(patient_id: str, meeting_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        if not PatientDirectory(db).link_meeting(actor, patient_id, meeting_id, linked=True):
            raise ServiceError(404, "PATIENT_OR_MEETING_NOT_FOUND", "Patient or meeting not found")
        return {"patientId": patient_id, "meetingId": meeting_id, "linked": True}

    @app.delete("/api/patients/{patient_id}/meetings/{meeting_id}")
    def unlink_patient_meeting(patient_id: str, meeting_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        if not PatientDirectory(db).link_meeting(actor, patient_id, meeting_id, linked=False):
            raise ServiceError(404, "PATIENT_OR_MEETING_NOT_FOUND", "Patient or meeting not found")
        return {"patientId": patient_id, "meetingId": meeting_id, "linked": False}

    @app.post("/api/meetings", status_code=201)
    def create_meeting(data: CreateMeeting, actor: dict = Depends(principal), db: Storage = Depends(store)):
        if actor["role"] == "reviewer":
            raise ServiceError(403, "ROLE_READ_ONLY", "Reviewer accounts cannot create meetings")
        item = data.model_dump()
        item["recordedAt"] = data.recordedAt.isoformat()
        try:
            meeting = db.create_meeting(actor, item)
        except ValueError as exc:
            raise ServiceError(422, "PATIENT_LINK_INVALID", "A selected patient is unavailable") from exc
        return meeting_record(meeting, db.meeting_patient_ids(meeting["id"], actor["organization_id"]))

    @app.get("/api/meetings")
    def list_meetings(q: str = "", limit: int = Query(default=20, ge=1, le=100),
                      offset: int = Query(default=0, ge=0), actor: dict = Depends(principal),
                      db: Storage = Depends(store)):
        rows, total = db.list_meetings(actor["id"], actor["organization_id"], query=q, limit=limit, offset=offset)
        return {"meetings": [meeting_record(row, db.meeting_patient_ids(row["id"], actor["organization_id"])) for row in rows], "total": total,
                "limit": limit, "offset": offset}

    @app.get("/api/meetings/{meeting_id}")
    def get_meeting(meeting_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting = meeting_or_404(meeting_id, actor, db)
        artifact = db.latest_artifact(meeting_id, actor["organization_id"])
        return {"meeting": meeting_record(meeting, db.meeting_patient_ids(meeting_id, actor["organization_id"])),
                "permission": db.meeting_permission(meeting_id, actor["id"], actor["organization_id"]),
                "asset": asset_record(db.latest_asset(meeting_id, actor["organization_id"])),
                "latestJob": db.latest_job_for_meeting(meeting_id, actor["organization_id"]),
                "segments": [segment_record(row) for row in db.get_segments(meeting_id, actor["organization_id"])],
                "decisions": db.get_meeting_decisions(meeting_id, actor["organization_id"]),
                "canUndoCorrection": db.can_undo_transcript_revision(meeting_id, actor["organization_id"], meeting["transcript_revision"]),
                "captures": db.list_open_captures(meeting_id, actor["organization_id"]),
                "artifact": artifact_record(artifact) if artifact else None}

    @app.delete("/api/meetings/{meeting_id}")
    def purge_meeting(meeting_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db)
        if db.meeting_permission(meeting_id, actor["id"], actor["organization_id"]) != "owner":
            raise ServiceError(403, "MEETING_OWNER_REQUIRED", "Only the meeting owner can delete this meeting")
        try:
            pending_files = db.purge_meeting(meeting_id, actor["organization_id"], actor["id"])
        except RuntimeError as exc:
            if str(exc) == "MEETING_PROCESSING":
                raise ServiceError(409, "MEETING_PROCESSING", "Stop or wait for active processing before deleting this meeting") from exc
            raise
        if pending_files is None:
            raise ServiceError(404, "MEETING_NOT_FOUND", "Meeting not found")
        return {"ok": True, "pendingFileCleanup": pending_files}

    @app.get("/api/meetings/{meeting_id}/audio")
    def play_meeting_audio(meeting_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db)
        asset = db.latest_asset(meeting_id, actor["organization_id"])
        if not asset:
            raise ServiceError(404, "AUDIO_NOT_FOUND", "Audio not found")
        try:
            path = db.resolve_key(asset["decoded_key"])
        except ValueError as exc:
            raise ServiceError(404, "AUDIO_NOT_FOUND", "Audio not found") from exc
        if not path.is_file():
            raise ServiceError(404, "AUDIO_NOT_FOUND", "Audio not found")
        return FileResponse(path, media_type="audio/wav", filename="notavra-audio.wav", content_disposition_type="inline")

    @app.post("/api/meetings/{meeting_id}/artifacts", status_code=201)
    def finalize_artifact(meeting_id: str, data: FinalizeArtifact,
                          actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting = meeting_or_404(meeting_id, actor, db, write=True)
        if actor["role"] == "reviewer":
            raise ServiceError(403, "ROLE_READ_ONLY", "Reviewer accounts cannot approve output")
        if not data.confirmHumanReview:
            raise ServiceError(422, "HUMAN_REVIEW_REQUIRED", "Explicitly confirm that you reviewed the transcript and actions")
        decisions = db.get_meeting_decisions(meeting_id, actor["organization_id"])
        if (not decisions or meeting["transcript_revision"] != data.transcriptRevision or
                decisions.get("transcriptRevision") != data.transcriptRevision):
            raise ServiceError(409, "ARTIFACT_SNAPSHOT_STALE", "Current transcript and decisions are not ready for approval")
        from .rendering import render_minutes_html
        approved_at = timestamp()
        content = render_minutes_html(meeting, db.get_segments(meeting_id, actor["organization_id"]), decisions,
                                      reviewer=actor["username"], approved_at=approved_at)
        artifact = db.create_artifact(meeting_id, actor["organization_id"], actor["id"],
                                      data.transcriptRevision, decisions, content)
        if not artifact:
            raise ServiceError(409, "ARTIFACT_SNAPSHOT_STALE", "Transcript or decisions changed; reload before approval")
        return {"artifact": artifact_record(artifact)}

    @app.get("/api/artifacts/{artifact_id}/content")
    def download_artifact(artifact_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        artifact = db.get_artifact(artifact_id, actor["organization_id"])
        if not artifact or artifact["status"] != "ready":
            raise ServiceError(404, "ARTIFACT_NOT_FOUND", "Artifact not found")
        meeting = meeting_or_404(artifact["meeting_id"], actor, db)
        latest = db.latest_artifact(meeting["id"], actor["organization_id"])
        if (not latest or latest["id"] != artifact_id or
                artifact["transcript_revision"] != meeting["transcript_revision"]):
            raise ServiceError(404, "ARTIFACT_NOT_FOUND", "Artifact not found")
        try:
            path = db.artifact_path(artifact["storage_key"])
        except FileNotFoundError as exc:
            raise ServiceError(404, "ARTIFACT_NOT_FOUND", "Artifact file not found") from exc
        if hashlib.sha256(path.read_bytes()).hexdigest() != artifact["sha256"]:
            raise ServiceError(503, "ARTIFACT_CHECKSUM_FAILED", "The approved artifact failed its integrity check")
        return FileResponse(path, media_type="text/html", filename=f"notavra-minutes-{artifact_id}.html")

    @app.put("/api/meetings/{meeting_id}/segments/{segment_id}")
    def revise_segment(meeting_id: str, segment_id: str, data: ReviseSegment,
                       actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db, write=True)
        if actor["role"] == "reviewer":
            raise ServiceError(403, "ROLE_READ_ONLY", "Reviewer accounts cannot edit transcripts")
        try:
            segment = db.revise_segment(meeting_id, actor["organization_id"], segment_id,
                                        actor["id"], data.transcriptRevision, data.text)
        except ValueError as exc:
            raise ServiceError(422, "TRANSCRIPT_TEXT_INVALID", str(exc)) from exc
        if not segment:
            raise ServiceError(409, "TRANSCRIPT_REVISION_CONFLICT", "Transcript changed; reload before editing")
        return segment_record(segment)

    @app.put("/api/meetings/{meeting_id}/segments")
    def revise_segments(meeting_id: str, data: ReviseSegments,
                        actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db, write=True)
        if actor["role"] == "reviewer":
            raise ServiceError(403, "ROLE_READ_ONLY", "Reviewer accounts cannot edit transcripts")
        try:
            segments = db.revise_segments(meeting_id, actor["organization_id"], actor["id"],
                                          data.transcriptRevision,
                                          [item.model_dump() for item in data.corrections])
        except ValueError as exc:
            raise ServiceError(422, "TRANSCRIPT_TEXT_INVALID", str(exc)) from exc
        if segments is None:
            raise ServiceError(409, "TRANSCRIPT_REVISION_CONFLICT", "Transcript changed; reload before editing")
        return {"transcriptRevision": data.transcriptRevision + 1,
                "segments": [segment_record(segment) for segment in segments]}

    @app.post("/api/meetings/{meeting_id}/transcript/undo")
    def undo_transcript_revision(meeting_id: str, data: UndoTranscriptRevision,
                                 actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db, write=True)
        if actor["role"] == "reviewer":
            raise ServiceError(403, "ROLE_READ_ONLY", "Reviewer accounts cannot edit transcripts")
        segments = db.undo_transcript_revision(meeting_id, actor["organization_id"], actor["id"],
                                               data.transcriptRevision)
        if segments is None:
            raise ServiceError(409, "TRANSCRIPT_REVISION_CONFLICT", "No matching correction revision can be undone")
        return {"transcriptRevision": data.transcriptRevision + 1,
                "segments": [segment_record(segment) for segment in segments]}

    @app.get("/api/meetings/{meeting_id}/grants")
    def get_meeting_grants(meeting_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db)
        if db.meeting_permission(meeting_id, actor["id"], actor["organization_id"]) != "owner":
            raise ServiceError(403, "GRANT_OWNER_REQUIRED", "Only the meeting owner can manage access")
        return {"grants": db.meeting_grants(meeting_id, actor["organization_id"])}

    @app.post("/api/meetings/{meeting_id}/grants", status_code=201)
    def grant_meeting_access(meeting_id: str, data: GrantMeetingAccess, actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db)
        if db.meeting_permission(meeting_id, actor["id"], actor["organization_id"]) != "owner":
            raise ServiceError(403, "GRANT_OWNER_REQUIRED", "Only the meeting owner can manage access")
        if not db.grant_meeting(meeting_id, actor["organization_id"], data.userId,
                                data.permission, actor["id"]):
            raise ServiceError(404, "USER_NOT_FOUND", "Account not found")
        return {"meetingId": meeting_id, "userId": data.userId, "permission": data.permission}

    @app.delete("/api/meetings/{meeting_id}/grants/{user_id}")
    def revoke_meeting_access(meeting_id: str, user_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db)
        if db.meeting_permission(meeting_id, actor["id"], actor["organization_id"]) != "owner":
            raise ServiceError(403, "GRANT_OWNER_REQUIRED", "Only the meeting owner can manage access")
        if user_id == actor["id"] or not db.revoke_meeting_grant(meeting_id, actor["organization_id"], user_id):
            raise ServiceError(404, "GRANT_NOT_FOUND", "Access grant not found")
        return {"ok": True}

    @app.get("/api/profiles")
    def get_profiles(actor: dict = Depends(principal)):
        from .models import resolve_profile
        gpu_memory = host_gpu_memory_gb()
        gpu_free_memory = host_gpu_free_memory_gb()
        available_ram = host_available_memory_gb()
        from .cuda_runtime import configure_cuda_dll_search
        cuda_runtime_ready, _ = configure_cuda_dll_search()
        choices = []
        for profile_id in ("laptop8", "hospital16", "cpu"):
            config = resolve_profile(profile_id)
            from .adapters.llm import _runtime_path
            asr_path = Path(config["models"]["asr"]["path"])
            llm_path = Path(config["models"]["llm"]["path"])
            llm_runtime_present = _runtime_path(config["models"]["llm"]).is_file()
            required_vram = float(config["limits"].get("max_vram_gb", 0))
            required_ram = float(config["limits"].get("min_available_ram_gb", 8))
            required_free_vram = float(config["limits"].get("min_free_vram_gb", 0))
            gpu_compatible = (profile_id == "cpu" or
                              (gpu_memory is not None and gpu_memory >= required_vram and
                               gpu_free_memory is not None and gpu_free_memory >= required_free_vram and
                               cuda_runtime_ready))
            compatible = (gpu_compatible and available_ram is not None and available_ram >= required_ram
                          and llm_runtime_present)
            choices.append({"id": profile_id, "hardware": config["hardware"],
                            "asrAlias": config["models"]["asr"]["alias"],
                            "llmAlias": config["models"]["llm"]["alias"],
                            "compatible": compatible, "hostVramGb": gpu_memory,
                            "hostFreeVramGb": gpu_free_memory,
                            "hostAvailableRamGb": available_ram, "requiredAvailableRamGb": required_ram,
                            "llmRuntimePresent": llm_runtime_present,
                            "asrFilesPresent": (asr_path / "model.bin").is_file(),
                            "llmFilePresent": llm_path.is_file()})
        return {"profiles": choices, "defaultProfileId": os.environ.get("MOM_PROFILE", "laptop8"), "verified": False}

    @app.post("/api/meetings/{meeting_id}/audio", status_code=201)
    async def upload_audio(
        meeting_id: str, request: Request, file: UploadFile = File(...),
        audio_track_index: int | None = Query(default=None, ge=0),
        actor: dict = Depends(principal), db: Storage = Depends(store),
    ):
        meeting_or_404(meeting_id, actor, db, write=True)
        asset_id = str(uuid.uuid4())
        source = db.asset_path(meeting_id, asset_id, ".source")
        decoded = db.asset_path(meeting_id, asset_id, ".wav")
        temporary = source.with_name(source.name + ".upload")
        size = 0
        digest = hashlib.sha256()
        recorded = False
        try:
            with temporary.open("xb") as output:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise ServiceError(413, "UPLOAD_TOO_LARGE", "The upload exceeds the 2 GiB limit")
                    digest.update(chunk)
                    output.write(chunk)
                output.flush()
                os.fsync(output.fileno())
            if size == 0:
                raise ServiceError(422, "EMPTY_UPLOAD", "The uploaded file is empty")
            os.replace(temporary, source)
            info = await asyncio.to_thread(decode, source, decoded, audio_track_index)
            details = {"id": asset_id, "source_key": db.relative_key(source), "decoded_key": db.relative_key(decoded),
                       "source_sha256": digest.hexdigest(), "size_bytes": size, **info}
            asset = db.create_asset(meeting_id, actor["organization_id"], details)
            recorded = True
            return asset_record(asset)
        except MediaError as exc:
            raise ServiceError(422, exc.code, str(exc), exc.details) from exc
        except OSError as exc:
            raise ServiceError(507, "STORAGE_UNAVAILABLE", "The recording could not be saved", retryable=True) from exc
        finally:
            await file.close()
            temporary.unlink(missing_ok=True)
            if not recorded:
                # A failed ingest must not leave an untracked copy of sensitive media.
                source.unlink(missing_ok=True)
                decoded.unlink(missing_ok=True)

    @app.post("/api/meetings/{meeting_id}/captures", status_code=201)
    def create_capture(meeting_id: str, data: CreateCapture, actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db, write=True)
        try:
            capture = db.create_capture_session(meeting_id, actor["organization_id"], actor["id"], data.contentType)
        except ValueError as exc:
            raise ServiceError(422, "CAPTURE_FORMAT_UNSUPPORTED", str(exc)) from exc
        return {"id": capture["id"], "state": capture["state"], "nextSequence": 0}

    @app.get("/api/captures/{capture_id}")
    def get_capture(capture_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        capture = db.get_capture_session(capture_id, actor["organization_id"])
        if not capture or not db.meeting_permission(capture["meeting_id"], actor["id"], actor["organization_id"]):
            raise ServiceError(404, "CAPTURE_NOT_FOUND", "Capture not found")
        return {"id": capture["id"], "meetingId": capture["meeting_id"], "state": capture["state"],
                "nextSequence": capture["next_sequence"], "receivedBytes": capture["received_bytes"],
                "errorCode": capture["error_code"]}

    @app.delete("/api/captures/{capture_id}")
    def delete_capture(capture_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        if not db.delete_capture(capture_id, actor["organization_id"], actor["id"]):
            raise ServiceError(404, "CAPTURE_NOT_FOUND", "Capture not found")
        return {"ok": True}

    @app.put("/api/captures/{capture_id}/chunks/{sequence}")
    async def upload_capture_chunk(capture_id: str, sequence: int, request: Request,
                                   actor: dict = Depends(principal), db: Storage = Depends(store)):
        if sequence < 0 or sequence > 2159:
            raise ServiceError(422, "CAPTURE_SEQUENCE_INVALID", "Capture chunk sequence is outside its limit")
        capture = db.get_capture_session(capture_id, actor["organization_id"])
        if not capture:
            raise ServiceError(404, "CAPTURE_NOT_FOUND", "Capture not found")
        meeting_or_404(capture["meeting_id"], actor, db, write=True)
        if request.headers.get("content-type", "").casefold() != capture["content_type"].casefold():
            raise ServiceError(415, "CAPTURE_FORMAT_CHANGED", "Capture chunk format does not match the session")
        chunks = []
        size = 0
        async for part in request.stream():
            size += len(part)
            if size > 32 * 1024 * 1024:
                raise ServiceError(413, "CAPTURE_CHUNK_TOO_LARGE", "A recording chunk exceeds 32 MiB")
            chunks.append(part)
        try:
            return db.store_capture_chunk(capture_id, actor["organization_id"], actor["id"],
                                          sequence, b"".join(chunks))
        except LookupError as exc:
            raise ServiceError(404, "CAPTURE_NOT_FOUND", "Capture not found") from exc
        except OverflowError as exc:
            raise ServiceError(413, "CAPTURE_TOO_LARGE", "The capture exceeds the 2 GiB limit") from exc
        except ValueError as exc:
            raise ServiceError(409, "CAPTURE_SEQUENCE_CONFLICT", str(exc)) from exc

    @app.post("/api/captures/{capture_id}/seal")
    async def seal_capture_route(capture_id: str, data: SealCapture,
                                 actor: dict = Depends(principal), db: Storage = Depends(store)):
        capture = db.get_capture_session(capture_id, actor["organization_id"])
        if not capture:
            raise ServiceError(404, "CAPTURE_NOT_FOUND", "Capture not found")
        meeting_or_404(capture["meeting_id"], actor, db, write=True)
        try:
            asset = await asyncio.to_thread(seal_capture, db, capture_id, actor["organization_id"],
                                            actor["id"], data.expectedSequenceCount)
        except CaptureError as exc:
            raise ServiceError(exc.status, exc.code, str(exc), retryable=exc.status >= 500) from exc
        return {"asset": asset_record(asset), "state": "sealed"}

    @app.post("/api/captures/{capture_id}/preview")
    async def preview_capture_window(capture_id: str, request: Request,
                                     profile_id: str = Query(alias="profileId"),
                                     language: str = Query(), start_ms: int = Query(ge=0),
                                     ownership_start_ms: int = Query(alias="ownershipStartMs", ge=0),
                                     ownership_end_ms: int = Query(alias="ownershipEndMs", gt=0),
                                     actor: dict = Depends(principal), db: Storage = Depends(store)):
        capture = db.get_capture_session(capture_id, actor["organization_id"])
        if not capture or capture["state"] != "capturing":
            raise ServiceError(404, "CAPTURE_NOT_FOUND", "Active capture not found")
        meeting_or_404(capture["meeting_id"], actor, db, write=True)
        if language not in {"ro", "ru", "en", "auto"}:
            raise ServiceError(422, "LANGUAGE_UNSUPPORTED", "Select Romanian, Russian, English or automatic detection")
        if request.headers.get("content-type", "").split(";", 1)[0].strip().casefold() != "audio/wav":
            raise ServiceError(415, "PREVIEW_FORMAT_UNSUPPORTED", "Live preview must be a mono 16 kHz PCM WAV window")
        payload = bytearray()
        async for part in request.stream():
            payload.extend(part)
            if len(payload) > 1_000_000:
                raise ServiceError(413, "PREVIEW_WINDOW_TOO_LARGE", "Live preview windows are limited to 30 seconds")
        try:
            with wave.open(io.BytesIO(payload), "rb") as wav:
                frames = wav.getnframes()
                if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 16000, "NONE"):
                    raise ValueError("Expected mono 16 kHz PCM16 audio")
                duration_ms = round(frames * 1000 / 16000)
                if frames < 16000 or frames > 30 * 16000:
                    raise ValueError("Window must be between one and 30 seconds")
                if len(wav.readframes(frames)) != frames * 2:
                    raise ValueError("PCM audio window is truncated")
        except (EOFError, wave.Error, ValueError) as exc:
            raise ServiceError(422, "PREVIEW_AUDIO_INVALID", str(exc)) from exc
        window_end = start_ms + duration_ms
        if ownership_start_ms < start_ms or ownership_end_ms > window_end or ownership_end_ms <= ownership_start_ms:
            raise ServiceError(422, "PREVIEW_OFFSET_INVALID", "Preview ownership offsets must fit within the audio window")

        from .models import ModelAssetError, validate_assets, resolve_profile
        from .adapters.asr import ASRError, asr_configuration_hash, transcribe_audio
        try:
            config = resolve_profile(profile_id, overrides={"asr": {"language": language}})
            minimum_ram = float(config.get("limits", {}).get("min_available_ram_gb", 8))
            available_ram = host_available_memory_gb()
            if available_ram is None or available_ram < minimum_ram:
                raise ServiceError(503, "SYSTEM_MEMORY_LOW", "Not enough free RAM for live recognition")
            asr = config["models"]["asr"]
            if asr.get("device") == "cuda":
                required_vram = float(config["limits"].get("max_vram_gb", 0))
                gpu_memory = host_gpu_memory_gb()
                if gpu_memory is None or gpu_memory < required_vram:
                    raise ServiceError(422, "PROFILE_INCOMPATIBLE", "Selected profile requires a compatible NVIDIA GPU")
                minimum_free_vram = float(config["limits"].get("min_free_vram_gb", 0))
                free_vram = host_gpu_free_memory_gb()
                if free_vram is None or free_vram < minimum_free_vram:
                    raise ServiceError(503, "GPU_MEMORY_LOW", "Not enough free GPU memory for live recognition")
                from .cuda_runtime import configure_cuda_dll_search
                ready, reason = configure_cuda_dll_search()
                if not ready:
                    raise ServiceError(503, "ASR_CUDA_RUNTIME_MISSING", reason or "CUDA runtime libraries are missing")
            validate_assets(config, kinds=("asr",))
            preview_dir = db.root / "temporary"
            preview_dir.mkdir(parents=True, exist_ok=True)
            preview_path = preview_dir / f"{uuid.uuid4()}.wav"
            try:
                preview_path.write_bytes(payload)
                with inference_device_lock(db.root):
                    result = await asyncio.to_thread(
                        transcribe_audio, preview_path,
                        {"id": capture["asset_id"], "duration_ms": window_end, "source_offset_ms": start_ms},
                        config)
            finally:
                preview_path.unlink(missing_ok=True)
        except InferenceBusy as exc:
            raise ServiceError(409, "LIVE_PREVIEW_BUSY", "Live recognition is busy; the saved recording is unaffected", retryable=True) from exc
        except ModelAssetError as exc:
            raise ServiceError(503, "MODEL_NOT_READY", "The selected local ASR model is missing or corrupt") from exc
        except ASRError as exc:
            raise ServiceError(503, exc.code, str(exc), retryable=True) from exc
        except (ValueError, KeyError, FileNotFoundError) as exc:
            raise ServiceError(422, "PROFILE_UNAVAILABLE", str(exc)) from exc
        except OSError as exc:
            raise ServiceError(507, "PREVIEW_STORAGE_UNAVAILABLE", "The temporary preview window could not be stored") from exc
        owned = []
        for segment in result["segments"]:
            if segment.get("words"):
                words = [dict(word) for word in segment["words"]
                         if ownership_start_ms <= (word["startMs"] + word["endMs"]) // 2 < ownership_end_ms]
                if not words:
                    continue
                for word in words:
                    word["startMs"] = max(ownership_start_ms, word["startMs"])
                    word["endMs"] = min(ownership_end_ms, word["endMs"])
                owned.append({**segment, "startMs": min(word["startMs"] for word in words),
                              "endMs": max(word["endMs"] for word in words),
                              "text": "".join(word["text"] for word in words), "words": words})
            elif ownership_start_ms <= (segment["startMs"] + segment["endMs"]) // 2 < ownership_end_ms:
                owned.append(segment)
        try:
            db.save_capture_preview_window(capture_id, actor["organization_id"], actor["id"],
                                           start_ms, ownership_end_ms, asr_configuration_hash(config),
                                           owned, result["metrics"])
        except (LookupError, ValueError) as exc:
            raise ServiceError(409, "CAPTURE_PREVIEW_STALE", "Capture ended before this preview could be saved", retryable=True) from exc
        return {"segments": owned, "startMs": start_ms, "endMs": window_end,
                "ownershipStartMs": ownership_start_ms, "ownershipEndMs": ownership_end_ms,
                "wallSeconds": result["metrics"]["wallSeconds"]}

    @app.post("/api/meetings/{meeting_id}/jobs", status_code=202)
    def create_job(data: CreateJob, meeting_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db, write=True)
        asset = db.latest_asset(meeting_id, actor["organization_id"])
        if not asset:
            raise ServiceError(409, "AUDIO_REQUIRED", "Upload or record audio before starting a job")
        from .models import ModelAssetError, validate_assets, resolve_profile
        try:
            config = resolve_profile(data.profileId, asr_alias=data.asrModelAlias,
                                     llm_alias=data.llmModelAlias,
                                     overrides={"asr": {"language": data.language}})
        except (ValueError, KeyError, FileNotFoundError) as exc:
            raise ServiceError(422, "PROFILE_UNAVAILABLE", str(exc)) from exc
        try:
            minimum_ram = float(config.get("limits", {}).get("min_available_ram_gb", 8))
            available_ram = host_available_memory_gb()
            if available_ram is None or available_ram < minimum_ram:
                raise ServiceError(503, "SYSTEM_MEMORY_LOW",
                                   f"At least {minimum_ram:g} GiB free RAM is required; close other apps and retry")
            if config["models"]["asr"].get("device") == "cuda":
                gpu_memory = host_gpu_memory_gb()
                required_vram = float(config["limits"].get("max_vram_gb", 0))
                if gpu_memory is None or gpu_memory < required_vram:
                    raise ServiceError(422, "PROFILE_INCOMPATIBLE", "This profile requires a compatible local NVIDIA GPU")
                gpu_free_memory = host_gpu_free_memory_gb()
                minimum_free_vram = float(config["limits"].get("min_free_vram_gb", 0))
                if gpu_free_memory is None or gpu_free_memory < minimum_free_vram:
                    raise ServiceError(503, "GPU_MEMORY_LOW",
                                       f"At least {minimum_free_vram:g} GiB free GPU memory is required; close other GPU apps and retry")
                from .cuda_runtime import configure_cuda_dll_search
                cuda_ready, cuda_issue = configure_cuda_dll_search()
                if not cuda_ready:
                    raise ServiceError(503, "ASR_CUDA_RUNTIME_MISSING", cuda_issue or "CUDA runtime libraries are missing")
            validate_assets(config, kinds=("asr", "llm"))
            from .adapters.llm import _runtime_path
            if not _runtime_path(config["models"]["llm"]).is_file():
                raise ServiceError(503, "LLM_RUNTIME_NOT_READY", "The selected local LLM runtime is missing")
        except ModelAssetError as exc:
            raise ServiceError(503, "MODEL_NOT_READY", "The selected local ASR model is missing or corrupt") from exc
        return job_record(db.create_or_get_job(meeting_id, actor["organization_id"], asset["id"], config))

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        job = db.get_job(job_id, actor["organization_id"])
        if not job or not db.meeting_permission(job["meeting_id"], actor["id"], actor["organization_id"]):
            raise ServiceError(404, "JOB_NOT_FOUND", "Job not found")
        return job_record(job)

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        current = db.get_job(job_id, actor["organization_id"])
        if not current or not db.meeting_permission(current["meeting_id"], actor["id"], actor["organization_id"]):
            raise ServiceError(404, "JOB_NOT_FOUND", "Job not found")
        if db.meeting_permission(current["meeting_id"], actor["id"], actor["organization_id"]) not in {"owner", "editor"}:
            raise ServiceError(403, "MEETING_READ_ONLY", "This account has read-only access")
        job = db.retry_job(job_id, actor["organization_id"])
        if not job:
            raise ServiceError(409, "JOB_NOT_RETRYABLE", "The job cannot be retried")
        return job_record(job)

    return app


app = create_app()
