import json
from datetime import datetime, timezone
from pydantic import BaseModel, ConfigDict, computed_field, field_validator


def utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt


class AuthProfileCreate(BaseModel):
    name: str
    storage_state_json: str


class AuthProfileResponse(BaseModel):
    """Session metadata for the dashboard.

    Deliberately omits `storage_state_json`: it holds live session cookies, and
    the UI only ever needs to know whether a usable session exists and when it
    lapses.
    """
    id: str
    project_id: str
    name: str
    expires_at: datetime | None = None
    model_config = ConfigDict(from_attributes=True)

    # Populated by the service from the stored state.
    cookie_count: int = 0
    origins: list[str] = []

    @field_validator('expires_at', mode='before')
    @classmethod
    def expires_at_utc(cls, v):
        # SQLite drops tzinfo; the value was stored as UTC.
        return utc(v) if isinstance(v, datetime) else v

    @computed_field
    @property
    def is_usable(self) -> bool:
        from app.execution.auth_manager import is_usable
        return is_usable(self.expires_at)

    @staticmethod
    def summarise(profile) -> dict:
        """Extract the non-secret bits of a stored storage_state."""
        try:
            state = json.loads(profile.storage_state_json)
        except (ValueError, TypeError):
            return {"cookie_count": 0, "origins": []}
        return {
            "cookie_count": len(state.get("cookies", [])),
            "origins": [o.get("origin", "") for o in state.get("origins", [])],
        }
