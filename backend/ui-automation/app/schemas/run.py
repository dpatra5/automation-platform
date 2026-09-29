from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List
from datetime import datetime, timezone
from app.models.models import StatusEnum, EvidenceTypeEnum, JiraSyncEnum


def _as_utc(v):
    """SQLite drops tzinfo; timestamps are stored as UTC, so label them as such.

    Without this the API emits offset-less ISO strings that browsers parse as
    local time, which skews every duration shown in the dashboard.
    """
    if isinstance(v, datetime) and v.tzinfo is None:
        return v.replace(tzinfo=timezone.utc)
    return v


class RunBase(BaseModel):
    status: str = "pending"
    trigger_source: Optional[str] = None

    @field_validator("status", mode="before")
    @classmethod
    def status_to_str(cls, v):
        if isinstance(v, StatusEnum):
            return v.value
        return v


class RunCreate(RunBase):
    pass


class StepResultResponse(BaseModel):
    id: str
    test_run_id: str
    step_id: str
    status: str
    duration_ms: Optional[int] = None
    screenshot_path: Optional[str] = None
    error_message: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

    @field_validator("status", mode="before")
    @classmethod
    def status_to_str(cls, v):
        if isinstance(v, StatusEnum):
            return v.value
        return v

    @field_validator("screenshot_path", mode="before")
    @classmethod
    def normalize_screenshot_path(cls, v):
        """Convert absolute filesystem paths to relative artifact paths."""
        if v and ("artifacts" in str(v)):
            # Extract 'artifacts/...' portion
            parts = str(v).replace("\\", "/")
            idx = parts.find("artifacts/")
            if idx >= 0:
                return parts[idx:]
        return v


class EvidenceResponse(BaseModel):
    id: str
    test_run_id: str
    type: str
    file_path: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

    @field_validator("created_at", mode="before")
    @classmethod
    def created_at_utc(cls, v):
        return _as_utc(v)

    @field_validator("type", mode="before")
    @classmethod
    def type_to_str(cls, v):
        if isinstance(v, EvidenceTypeEnum):
            return v.value
        return v

    @field_validator("file_path", mode="before")
    @classmethod
    def normalize_file_path(cls, v):
        """Convert absolute filesystem paths to relative artifact paths."""
        if v and ("artifacts" in str(v)):
            parts = str(v).replace("\\", "/")
            idx = parts.find("artifacts/")
            if idx >= 0:
                return parts[idx:]
        return v


class RunResponse(RunBase):
    id: str
    test_case_id: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    error_message: Optional[str] = None
    batch_id: Optional[str] = None
    batch_order: Optional[int] = None
    jira_issue_key: Optional[str] = None
    jira_status: Optional[str] = None
    jira_error: Optional[str] = None
    step_results: List[StepResultResponse] = []
    evidences: List[EvidenceResponse] = []
    model_config = ConfigDict(from_attributes=True)

    @field_validator("started_at", "finished_at", mode="before")
    @classmethod
    def timestamps_utc(cls, v):
        return _as_utc(v)

    @field_validator("jira_status", mode="before")
    @classmethod
    def jira_status_to_str(cls, v):
        if isinstance(v, JiraSyncEnum):
            return v.value
        return v
