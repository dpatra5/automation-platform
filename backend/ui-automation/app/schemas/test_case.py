from pydantic import BaseModel, ConfigDict, field_validator
from typing import Optional, List
from datetime import datetime
from app.models.models import ActionEnum, SelectorStrategyEnum


class StepBase(BaseModel):
    order_index: int
    action: str
    selector: str = ""
    selector_strategy: str = "css"
    value: Optional[str] = None
    assertion_type: Optional[str] = None
    expected_value: Optional[str] = None
    # Set when the element lives inside an iframe rather than the main page.
    frame_url: Optional[str] = None
    # JSON the recorder wrote describing the element - tag, role, label, and
    # other ways to reach it - so replay survives the page being rebuilt.
    element_meta: Optional[str] = None
    # Exit criteria run after every ordinary step, whatever their order_index.
    is_exit_criteria: bool = False

    @field_validator("action", mode="before")
    @classmethod
    def action_to_str(cls, v):
        if isinstance(v, ActionEnum):
            return v.value
        # Recorded steps arrive from the browser extension: reject anything the
        # runner has no handler for rather than storing an unplayable step.
        try:
            return ActionEnum(v).value
        except ValueError:
            raise ValueError(
                f"Unknown action '{v}'. Allowed: {', '.join(a.value for a in ActionEnum)}"
            ) from None

    @field_validator("selector_strategy", mode="before")
    @classmethod
    def strategy_to_str(cls, v):
        if isinstance(v, SelectorStrategyEnum):
            return v.value
        try:
            return SelectorStrategyEnum(v).value
        except ValueError:
            raise ValueError(
                f"Unknown selector strategy '{v}'. Allowed: "
                f"{', '.join(s.value for s in SelectorStrategyEnum)}"
            ) from None


class StepCreate(StepBase):
    pass


class StepUpsert(StepBase):
    """A step coming back from the editor.

    Saving replaces the whole list, so the id has to survive the round trip:
    step results point at it, and losing it would cascade away the history of
    every run that already used this step.
    """

    id: Optional[str] = None


class StepResponse(StepBase):
    id: str
    test_case_id: str
    model_config = ConfigDict(from_attributes=True)


class TestCaseBase(BaseModel):
    name: str
    description: Optional[str] = None
    start_url: str = ""


class TestCaseCreate(TestCaseBase):
    steps: List[StepCreate] = []


class TestCaseUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    start_url: Optional[str] = None
    steps: Optional[List[StepUpsert]] = None


class TestCaseResponse(TestCaseBase):
    id: str
    project_id: str
    created_at: datetime
    steps: List[StepResponse] = []
    model_config = ConfigDict(from_attributes=True)
