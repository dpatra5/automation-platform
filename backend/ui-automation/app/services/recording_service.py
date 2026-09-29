import json
import logging
import uuid
from typing import Optional
from app.schemas.recording import RecordingPayload
from app.models.models import TestCase, AuthProfile, ActionEnum, SelectorStrategyEnum
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.step_repo import StepRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.auth_profile_repo import AuthProfileRepository
from app.execution.auth_manager import earliest_expiry
from app.exceptions import NotFoundError, RewindError

logger = logging.getLogger(__name__)


class RecordingService:
    """Service for handling UI recording sessions."""

    def __init__(
        self,
        test_case_repo: TestCaseRepository,
        step_repo: StepRepository,
        project_repo: ProjectRepository,
        auth_profile_repo: Optional[AuthProfileRepository] = None,
    ):
        self.test_case_repo = test_case_repo
        self.step_repo = step_repo
        self.project_repo = project_repo
        self.auth_profile_repo = auth_profile_repo

    def generate_session_token(self) -> str:
        """Generate a new unique session token for recording."""
        return str(uuid.uuid4())

    async def create_from_recording(self, payload: RecordingPayload) -> TestCase:
        """Create a TestCase and its Steps from a recording payload."""
        if not await self.project_repo.get_by_id(payload.project_id):
            raise NotFoundError("Project not found")
        if not payload.steps:
            raise RewindError("The recording contained no steps")

        tc = await self.test_case_repo.create({
            "name": payload.name,
            "start_url": payload.start_url,
            "project_id": payload.project_id,
        })

        for order_index, step_in in enumerate(payload.steps):
            step_data = step_in.model_dump()
            step_data["order_index"] = order_index
            step_data["test_case_id"] = tc.id
            # The enum column keys off member names, not values ("assert_" vs
            # "assert"), so hand it members rather than raw strings.
            step_data["action"] = ActionEnum(step_data["action"])
            step_data["selector_strategy"] = SelectorStrategyEnum(step_data["selector_strategy"])
            await self.step_repo.create(step_data)

        if payload.storage_state:
            await self._save_session(payload.project_id, payload.storage_state)

        test_case = await self.test_case_repo.get_with_steps(tc.id)
        if not test_case:
            raise NotFoundError("Test case creation failed")

        return test_case

    async def _save_session(self, project_id: str, storage_state: dict) -> Optional[AuthProfile]:
        """Store the browser session so replayed runs start signed in.

        Only cookies and localStorage are kept - never the credentials typed
        during sign-in, which the recorder does not capture in the first place.
        """
        if not self.auth_profile_repo:
            return None

        state_json = json.dumps(storage_state)
        expires_at = earliest_expiry(state_json)
        data = {
            "name": "Recorded session",
            "storage_state_json": state_json,
            "expires_at": expires_at,
        }

        existing = await self.auth_profile_repo.get_by_project_id(project_id)
        if existing:
            profile = await self.auth_profile_repo.update(existing, data)
        else:
            profile = await self.auth_profile_repo.create({"project_id": project_id, **data})

        cookies = len(storage_state.get("cookies", []))
        logger.info(
            f"Saved session for project {project_id}: {cookies} cookies, "
            f"expires {expires_at.isoformat() if expires_at else 'with the browser session'}"
        )
        return profile
