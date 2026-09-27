"""Request and response shapes at the local HTTP boundary."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CreateMeeting(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contractVersion: Literal["1.0"] = "1.0"
    title: str = Field(min_length=1, max_length=240)
    recordedAt: datetime
    timeZone: str = Field(min_length=1, max_length=64)
    outputLanguage: Literal["ro", "ru", "en"]
    patientLinkIds: list[str] = Field(default_factory=list, max_length=50)
    meetingType: str | None = Field(default=None, max_length=80)

    @field_validator("recordedAt")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recordedAt needs an explicit time zone offset")
        return value


class ReviseSegment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcriptRevision: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=5000)


class SegmentCorrection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    segmentId: str = Field(min_length=1, max_length=128)
    text: str = Field(min_length=1, max_length=5000)


class ReviseSegments(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcriptRevision: int = Field(ge=1)
    corrections: list[SegmentCorrection] = Field(min_length=1, max_length=500)


class UndoTranscriptRevision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcriptRevision: int = Field(ge=1)


class CreateJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profileId: str | None = None
    asrModelAlias: str | None = None
    llmModelAlias: str | None = None
    language: Literal["auto", "ro", "ru", "en"] = "auto"


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


class SetupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)


class CreateAccount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=12, max_length=256)
    role: Literal["clinician", "reviewer", "administrator"]


class SetAccountActive(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool


class GrantMeetingAccess(BaseModel):
    model_config = ConfigDict(extra="forbid")

    userId: str = Field(min_length=1, max_length=128)
    permission: Literal["editor", "viewer"]


class CreatePatient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    displayName: str = Field(min_length=1, max_length=160)
    hospitalReference: str | None = Field(default=None, max_length=120)
    status: Literal["active", "inactive"] = "active"


class UpdatePatient(BaseModel):
    model_config = ConfigDict(extra="forbid")

    displayName: str | None = Field(default=None, min_length=1, max_length=160)
    hospitalReference: str | None = Field(default=None, max_length=120)
    status: Literal["active", "inactive"] | None = None


class FinalizeArtifact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcriptRevision: int = Field(ge=1)
    confirmHumanReview: bool


class ReviewDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcriptRevision: int = Field(ge=0)
    reviewStatus: Literal["needs_review", "accepted", "excluded"]
    status: Literal["proposed", "confirmed", "rejected", "cancelled", "unresolved"]
    text: str = Field(min_length=1, max_length=1200)
    ownerLabel: str | None = Field(default=None, max_length=240)
    originalDateExpression: str | None = Field(default=None, max_length=240)


class ReviewTranscriptIssue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transcriptRevision: int = Field(ge=1)
    reviewStatus: Literal["accepted", "deferred"]


class RetentionPolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    audioDays: int | None = Field(ge=1, le=3650)
    transcriptDays: int | None = Field(ge=1, le=3650)
    artifactDays: int | None = Field(ge=1, le=3650)
    voiceTemplateDays: int | None = Field(ge=1, le=3650)


class CreateCapture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contentType: Literal["audio/webm", "audio/webm;codecs=opus", "audio/mp4", "audio/wav"]


class SealCapture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expectedSequenceCount: int = Field(ge=1, le=2160)


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    retryable: bool
    requestId: str
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
