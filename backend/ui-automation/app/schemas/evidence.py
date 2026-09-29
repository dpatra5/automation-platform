from pydantic import BaseModel, ConfigDict, field_validator
from datetime import datetime
from app.models.models import EvidenceTypeEnum


class EvidenceBase(BaseModel):
    test_run_id: str
    type: str
    file_path: str

    @field_validator('type', mode='before')
    @classmethod
    def type_to_str(cls, v):
        if isinstance(v, EvidenceTypeEnum):
            return v.value
        return v


class EvidenceResponse(EvidenceBase):
    id: str
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)
