from pydantic import BaseModel, ConfigDict, field_validator
from typing import List, Optional
from datetime import datetime

from app.models.models import JiraSyncEnum, StatusEnum
from app.schemas.run import RunResponse, _as_utc


class RunBatchCreate(BaseModel):
    """Test cases to replay, in the order they should run."""

    test_case_ids: List[str]
    name: Optional[str] = None


class RunBatchResponse(BaseModel):
    id: str
    project_id: Optional[str] = None
    name: str
    status: str
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None
    trigger_source: Optional[str] = None
    error_message: Optional[str] = None
    #: Consolidated HTML report, served from the artifacts route.
    report_path: Optional[str] = None
    jira_issue_key: Optional[str] = None
    jira_status: Optional[str] = None
    jira_error: Optional[str] = None
    runs: List[RunResponse] = []
    model_config = ConfigDict(from_attributes=True)

    @field_validator("status", mode="before")
    @classmethod
    def status_to_str(cls, v):
        if isinstance(v, StatusEnum):
            return v.value
        return v

    @field_validator("jira_status", mode="before")
    @classmethod
    def jira_status_to_str(cls, v):
        if isinstance(v, JiraSyncEnum):
            return v.value
        return v

    @field_validator("started_at", "finished_at", mode="before")
    @classmethod
    def timestamps_utc(cls, v):
        return _as_utc(v)
