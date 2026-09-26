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
    patientLinkIds: list[str] = Field(default_factory=list)
    meetingType: str | None = Field(default=None, max_length=80)

    @field_validator("recordedAt")
    @classmethod
    def require_offset(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("recordedAt needs an explicit time zone offset")
        return value


class CreateJob(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profileId: str | None = None
    asrModelAlias: str | None = None
    llmModelAlias: str | None = None


class LoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=256)


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


class ErrorEnvelope(BaseModel):
    code: str
    message: str
    retryable: bool
    requestId: str
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)
