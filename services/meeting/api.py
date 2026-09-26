"""Loopback HTTP API for durable local meeting ingest and job status."""

import asyncio
import hashlib
import json
import os
import uuid
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, Query, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

from .contracts import CreateJob, CreateMeeting, ErrorEnvelope
from .media import MAX_UPLOAD_BYTES, MediaError, decode
from .storage import Storage


class ServiceError(Exception):
    def __init__(self, status: int, code: str, message: str, details: dict | None = None, retryable: bool = False):
        self.status = status
        self.code = code
        self.message = message
        self.details = details or {}
        self.retryable = retryable


def meeting_record(row: dict) -> dict:
    return {"id": row["id"], "organizationId": row["organization_id"],
            "title": row["title"], "recordedAt": row["recorded_at"], "timeZone": row["time_zone"],
            "meetingType": row["meeting_type"], "suggestedMeetingType": None,
            "outputLanguage": row["output_language"], "patientLinkIds": [], "participantIds": [],
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


def create_app(data_root: Path | None = None) -> FastAPI:
    app = FastAPI(title="Secure MOM local meeting service", version="0.1.0", docs_url=None, redoc_url=None)
    app.state.store = Storage(data_root)

    @app.middleware("http")
    async def request_id(request: Request, call_next):
        request.state.request_id = str(uuid.uuid4())
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

    def principal(request: Request, x_demo_principal: str | None = Header(default=None)) -> dict:
        # PBI-005 replaces this hook. Demo access requires an explicit local-only opt-in.
        host = request.client.host if request.client else ""
        if os.environ.get("MOM_SYNTHETIC_DEV") == "1" and host in {"127.0.0.1", "::1", "testclient"} and x_demo_principal == "synthetic-demo":
            return {"id": "user-demo-001", "organization_id": "org-demo"}
        raise ServiceError(403, "ACCESS_DENIED", "Local authentication is required")

    def meeting_or_404(meeting_id: str, actor: dict, db: Storage) -> dict:
        meeting = db.get_meeting(meeting_id, actor["organization_id"])
        if not meeting:
            raise ServiceError(404, "MEETING_NOT_FOUND", "Meeting not found")
        return meeting

    @app.get("/api/health")
    def health():
        return {"status": "ok", "service": "meeting"}

    @app.post("/api/meetings", status_code=201)
    def create_meeting(data: CreateMeeting, actor: dict = Depends(principal), db: Storage = Depends(store)):
        if data.patientLinkIds:
            raise ServiceError(422, "PATIENT_LINKS_UNAVAILABLE", "Patient links require the access service")
        item = data.model_dump()
        item["recordedAt"] = data.recordedAt.isoformat()
        return meeting_record(db.create_meeting(actor, item))

    @app.get("/api/meetings/{meeting_id}")
    def get_meeting(meeting_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting = meeting_or_404(meeting_id, actor, db)
        return {"meeting": meeting_record(meeting),
                "asset": asset_record(db.latest_asset(meeting_id, actor["organization_id"])),
                "segments": [segment_record(row) for row in db.get_segments(meeting_id, actor["organization_id"])]}

    @app.get("/api/profiles")
    def get_profiles(actor: dict = Depends(principal)):
        from .models import resolve_profile
        choices = []
        for profile_id in ("laptop8", "hospital16", "cpu"):
            config = resolve_profile(profile_id)
            asr_path = Path(config["models"]["asr"]["path"])
            llm_path = Path(config["models"]["llm"]["path"])
            choices.append({"id": profile_id, "hardware": config["hardware"],
                            "asrAlias": config["models"]["asr"]["alias"],
                            "llmAlias": config["models"]["llm"]["alias"],
                            "asrFilesPresent": (asr_path / "model.bin").is_file(),
                            "llmFilePresent": llm_path.is_file()})
        return {"profiles": choices, "verified": False}

    @app.post("/api/meetings/{meeting_id}/audio", status_code=201)
    async def upload_audio(
        meeting_id: str, request: Request, file: UploadFile = File(...),
        audio_track_index: int | None = Query(default=None, ge=0),
        actor: dict = Depends(principal), db: Storage = Depends(store),
    ):
        meeting_or_404(meeting_id, actor, db)
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

    @app.post("/api/meetings/{meeting_id}/jobs", status_code=202)
    def create_job(data: CreateJob, meeting_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        meeting_or_404(meeting_id, actor, db)
        asset = db.latest_asset(meeting_id, actor["organization_id"])
        if not asset:
            raise ServiceError(409, "AUDIO_REQUIRED", "Upload or record audio before starting a job")
        from .models import ModelAssetError, validate_assets, resolve_profile
        try:
            config = resolve_profile(data.profileId, asr_alias=data.asrModelAlias,
                                     llm_alias=data.llmModelAlias)
        except (ValueError, KeyError, FileNotFoundError) as exc:
            raise ServiceError(422, "PROFILE_UNAVAILABLE", str(exc)) from exc
        try:
            validate_assets(config, kinds=("asr",))
        except ModelAssetError as exc:
            raise ServiceError(503, "MODEL_NOT_READY", "The selected local ASR model is missing or corrupt") from exc
        return job_record(db.create_or_get_job(meeting_id, actor["organization_id"], asset["id"], config))

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        job = db.get_job(job_id, actor["organization_id"])
        if not job:
            raise ServiceError(404, "JOB_NOT_FOUND", "Job not found")
        return job_record(job)

    @app.post("/api/jobs/{job_id}/retry", status_code=202)
    def retry_job(job_id: str, actor: dict = Depends(principal), db: Storage = Depends(store)):
        job = db.retry_job(job_id, actor["organization_id"])
        if not job:
            raise ServiceError(409, "JOB_NOT_RETRYABLE", "The job cannot be retried")
        return job_record(job)

    return app


app = create_app()
