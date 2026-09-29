from typing import List, Optional
from app.schemas.test_case import TestCaseCreate, TestCaseUpdate
from app.models.models import TestCase, Step, ActionEnum, SelectorStrategyEnum
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.step_repo import StepRepository
from app.repositories.project_repo import ProjectRepository
from app.services.script_service import carry_over, parse_script, render_script
from app.exceptions import NotFoundError

# Anything else in an incoming step dict is a field the dashboard carries for
# its own bookkeeping; passing it to the model would raise.
STEP_FIELDS = {c.name for c in Step.__table__.columns}


class TestCaseService:
    """Service for TestCase operations."""

    def __init__(
        self,
        test_case_repo: TestCaseRepository,
        step_repo: StepRepository,
        project_repo: ProjectRepository,
    ):
        self.test_case_repo = test_case_repo
        self.step_repo = step_repo
        self.project_repo = project_repo

    async def get_by_project(self, project_id: str) -> List[TestCase]:
        """Get all test cases for a project."""
        return await self.test_case_repo.get_by_project_id(project_id)

    async def get_test_case(self, test_case_id: str) -> TestCase:
        """Get a single test case with steps."""
        tc = await self.test_case_repo.get_with_steps(test_case_id)
        if not tc:
            raise NotFoundError("Test case not found")
        return tc

    async def create_test_case(
        self, project_id: str, tc_in: TestCaseCreate
    ) -> TestCase:
        """Create a test case."""
        if not await self.project_repo.get_by_id(project_id):
            raise NotFoundError("Project not found")

        tc_data = tc_in.model_dump(exclude={"steps"})
        tc_data["project_id"] = project_id
        tc = await self.test_case_repo.create(tc_data)

        for step_in in tc_in.steps:
            step_data = step_in.model_dump()
            step_data["test_case_id"] = tc.id
            # Convert string enums to actual enum values for ORM
            step_data["action"] = ActionEnum(step_data["action"])
            step_data["selector_strategy"] = SelectorStrategyEnum(
                step_data["selector_strategy"]
            )
            await self.step_repo.create(step_data)

        return await self.get_test_case(tc.id)

    async def update_test_case(self, test_case_id: str, update_data: dict) -> TestCase:
        """Update a test case partially."""
        tc = await self.get_test_case(test_case_id)

        # Handle steps update separately
        steps_data = update_data.pop("steps", None)

        # Update scalar fields
        update_fields = {}
        for k, v in update_data.items():
            if hasattr(tc, k) and k != "id":
                update_fields[k] = v

        if update_fields:
            await self.test_case_repo.update(tc, update_fields)

        # If steps were provided, replace them all
        if steps_data is not None:
            # Delete existing steps
            for old_step in list(tc.steps):
                await self.step_repo.delete(old_step)

            # Create new steps
            for order_index, step_item in enumerate(steps_data):
                raw = (
                    step_item if isinstance(step_item, dict) else step_item.model_dump()
                )
                step_dict = {
                    k: v for k, v in raw.items() if k in STEP_FIELDS and v is not None
                }
                step_dict["test_case_id"] = test_case_id
                step_dict.setdefault("order_index", order_index)
                step_dict["selector"] = step_dict.get("selector") or ""
                step_dict["is_exit_criteria"] = bool(raw.get("is_exit_criteria"))
                step_dict["action"] = ActionEnum(step_dict["action"])
                step_dict["selector_strategy"] = SelectorStrategyEnum(
                    step_dict.get("selector_strategy", "css")
                )
                await self.step_repo.create(step_dict)

        return await self.get_test_case(test_case_id)

    async def delete_test_case(self, test_case_id: str) -> None:
        """Delete a test case."""
        tc = await self.get_test_case(test_case_id)
        await self.test_case_repo.delete(tc)

    async def get_script(self, test_case_id: str) -> str:
        """The test case written out as an editable script."""
        return render_script(await self.get_test_case(test_case_id))

    async def update_from_script(self, test_case_id: str, source: str) -> TestCase:
        """Replace the steps with the ones the script describes.

        Raises `ScriptError` - reported as a 400 with the offending line - when
        the script says something that is not a step, rather than saving a test
        case with part of the flow silently missing.
        """
        tc = await self.get_test_case(test_case_id)
        steps = carry_over(parse_script(source), list(tc.steps))
        return await self.update_test_case(test_case_id, {"steps": steps})
