from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional
from datetime import datetime


def _tidy_jira_key(v):
    """Keys are upper-case, and an empty box means no key rather than ''."""
    if v is None:
        return None
    key = str(v).strip().upper()
    return key or None


class ProjectBase(BaseModel):
    name: str
    base_url: str
    description: Optional[str] = None
    # Optional Jira "Test Execution" issue, e.g. JGQE-23122. Verified against
    # Jira before it is stored.
    jira_key: Optional[str] = None

    _clean_key = field_validator("jira_key", mode="before")(_tidy_jira_key)


class ProjectCreate(ProjectBase):
    pass


class ProjectUpdate(BaseModel):
    name: Optional[str] = None
    base_url: Optional[str] = None
    description: Optional[str] = None
    jira_key: Optional[str] = None

    _clean_key = field_validator("jira_key", mode="before")(_tidy_jira_key)


class ProjectResponse(ProjectBase):
    id: str
    created_at: datetime
    test_case_count: int = 0
    last_run_status: Optional[str] = None
    #: Deep link to the linked issue, or None when no key is set.
    jira_browse_url: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)
