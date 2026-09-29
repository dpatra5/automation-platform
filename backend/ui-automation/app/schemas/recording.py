from pydantic import BaseModel, Field
from typing import Any, Dict, List, Optional
from app.schemas.test_case import StepCreate

class SessionTokenResponse(BaseModel):
    token: str

class RecordingPayload(BaseModel):
    session_token: str
    project_id: str
    name: str
    start_url: str
    steps: List[StepCreate] = []
    # Playwright storage_state captured at the end of the session: cookies plus
    # per-origin localStorage. Lets a replayed run start already signed in.
    storage_state: Optional[Dict[str, Any]] = Field(default=None)
