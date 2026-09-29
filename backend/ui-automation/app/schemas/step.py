from pydantic import BaseModel, ConfigDict
from typing import Optional
from app.models.models import ActionEnum, SelectorStrategyEnum


class StepBase(BaseModel):
    order_index: int
    action: ActionEnum
    selector: str
    selector_strategy: SelectorStrategyEnum
    value: Optional[str] = None
    assertion_type: Optional[str] = None
    expected_value: Optional[str] = None
    frame_url: Optional[str] = None
    # JSON describing the element, used to find it again when the page changed.
    element_meta: Optional[str] = None
    is_exit_criteria: bool = False


class StepCreate(StepBase):
    pass


class StepResponse(StepBase):
    id: str
    test_case_id: str
    model_config = ConfigDict(from_attributes=True)
