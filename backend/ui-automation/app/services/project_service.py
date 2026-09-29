from typing import List, Optional
from sqlalchemy import delete, func, select
from app.schemas.project import ProjectCreate
from app.schemas.auth_profile import AuthProfileCreate, AuthProfileResponse
from app.models.models import (
    AuthProfile,
    Evidence,
    Project,
    RunBatch,
    StatusEnum,
    Step,
    StepResult,
    TestCase,
    TestRun,
)
from app.repositories.project_repo import ProjectRepository
from app.repositories.auth_profile_repo import AuthProfileRepository
from app.execution.auth_manager import earliest_expiry
from app.services.artifacts import remove_batch_artifacts, remove_run_artifacts
from app.integrations.jira_client import (
    JiraError,
    get_jira_client,
    normalise_issue_key,
    require_jira_client,
)
from app.exceptions import NotFoundError, RewindError


class ProjectService:
    """Service layer for Project operations."""

    def __init__(
        self, project_repo: ProjectRepository, auth_repo: AuthProfileRepository
    ):
        self.project_repo = project_repo
        self.auth_repo = auth_repo

    async def get_projects(self) -> List[Project]:
        """Fetch all projects with computed stats."""
        projects = await self.project_repo.get_all()
        for p in projects:
            await self._attach_stats(p)
        return projects

    async def get_project(self, project_id: str) -> Project:
        """Fetch a specific project."""
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundError(f"Project {project_id} not found")
        await self._attach_stats(project)
        return project

    async def create_project(self, project_in: ProjectCreate) -> Project:
        """Create a new project, verifying its Jira key first if one was given."""
        data = project_in.model_dump()
        if data.get("jira_key"):
            await self.verify_jira_key(data["jira_key"])
        project = await self.project_repo.create(data)
        await self._attach_stats(project)
        return project

    async def update_project(self, project_id: str, changes: dict) -> Project:
        """Apply a partial update. A new Jira key is verified before it sticks."""
        project = await self.get_project(project_id)

        if "jira_key" in changes:
            key = normalise_issue_key(changes["jira_key"])
            changes["jira_key"] = key
            # Re-checking an unchanged key would make an unrelated edit fail
            # whenever Jira happens to be down.
            if key and key != project.jira_key:
                await self.verify_jira_key(key)

        fields = {k: v for k, v in changes.items() if hasattr(project, k) and k != "id"}
        if fields:
            await self.project_repo.update(project, fields)
        await self._attach_stats(project)
        return project

    @staticmethod
    async def verify_jira_key(jira_key: str) -> dict:
        """Confirm the key names a real Test Execution issue this token can see.

        Raises JiraError with a sentence explaining what to change, which the
        API turns into a 400.
        """
        key = normalise_issue_key(jira_key)
        if not key:
            raise JiraError("Enter a Jira issue key, or leave the field empty.")
        return await require_jira_client().resolve_test_execution(key)

    async def set_auth_profile(
        self, project_id: str, auth_in: AuthProfileCreate
    ) -> AuthProfile:
        """Set auth profile for a project."""
        await self.get_project(project_id)
        data = auth_in.model_dump()
        data["expires_at"] = earliest_expiry(data["storage_state_json"])

        existing = await self.auth_repo.get_by_project_id(project_id)
        if existing:
            profile = await self.auth_repo.update(existing, data)
        else:
            profile = await self.auth_repo.create({"project_id": project_id, **data})
        return self._with_summary(profile)

    async def get_auth_profile(self, project_id: str) -> Optional[AuthProfile]:
        """The stored session for a project, or None."""
        await self.get_project(project_id)
        profile = await self.auth_repo.get_by_project_id(project_id)
        return self._with_summary(profile) if profile else None

    async def clear_auth_profile(self, project_id: str) -> None:
        """Forget the stored session (it holds live cookies)."""
        profile = await self.auth_repo.get_by_project_id(project_id)
        if profile:
            await self.auth_repo.delete(profile)

    async def delete_project(self, project_id: str) -> None:
        """Delete a project and everything recorded under it.

        Test cases, their steps, runs, step results and evidence rows all go,
        and so do the evidence directories on disk, which nothing else would
        ever reach again. Each table is cleared by name rather than left to a
        foreign-key cascade: whether the database enforces one is a matter of
        configuration, and a half-deleted project is worse than a slow one.

        A run still in flight is refused - it is writing evidence for a test
        case this would delete underneath it.
        """
        project = await self.project_repo.get_by_id(project_id)
        if not project:
            raise NotFoundError(f"Project {project_id} not found")

        session = self.project_repo.session
        cases = select(TestCase.id).where(TestCase.project_id == project_id)
        runs = select(TestRun.id).where(TestRun.test_case_id.in_(cases))

        live = await session.execute(
            select(func.count(TestRun.id)).where(
                TestRun.test_case_id.in_(cases), TestRun.status == StatusEnum.running
            )
        )
        if live.scalar():
            raise RewindError(
                "A run in this project is still going. Wait for it to finish "
                "before deleting the project."
            )

        # Collected before the rows go, so the files can still be found.
        run_ids = list((await session.execute(runs)).scalars().all())
        batch_ids = list(
            (
                await session.execute(
                    select(RunBatch.id).where(RunBatch.project_id == project_id)
                )
            )
            .scalars()
            .all()
        )

        await session.execute(delete(Evidence).where(Evidence.test_run_id.in_(runs)))
        await session.execute(
            delete(StepResult).where(StepResult.test_run_id.in_(runs))
        )
        await session.execute(delete(TestRun).where(TestRun.test_case_id.in_(cases)))
        await session.execute(delete(Step).where(Step.test_case_id.in_(cases)))
        await session.execute(delete(TestCase).where(TestCase.project_id == project_id))
        await session.execute(delete(RunBatch).where(RunBatch.project_id == project_id))
        await session.execute(
            delete(AuthProfile).where(AuthProfile.project_id == project_id)
        )
        await session.delete(project)
        await session.commit()

        for run_id in run_ids:
            remove_run_artifacts(run_id)
        for batch_id in batch_ids:
            remove_batch_artifacts(batch_id)

    @staticmethod
    def _with_summary(profile: AuthProfile) -> AuthProfile:
        """Attach the non-secret counts the response schema reports."""
        for key, value in AuthProfileResponse.summarise(profile).items():
            setattr(profile, key, value)
        return profile

    async def _attach_stats(self, project: Project) -> None:
        """Attach test_case_count, last_run_status and the Jira deep link."""
        from sqlalchemy import select, func
        from app.models.models import TestCase, TestRun, StatusEnum

        session = self.project_repo.session

        # Count test cases
        result = await session.execute(
            select(func.count(TestCase.id)).where(TestCase.project_id == project.id)
        )
        project.test_case_count = result.scalar() or 0

        # Get last run status
        result = await session.execute(
            select(TestRun.status)
            .join(TestCase, TestRun.test_case_id == TestCase.id)
            .where(TestCase.project_id == project.id)
            .order_by(TestRun.started_at.desc())
            .limit(1)
        )
        last_status = result.scalar()
        project.last_run_status = last_status.value if last_status else None

        client = get_jira_client()
        project.jira_browse_url = (
            client.browse_url(project.jira_key) if client and project.jira_key else None
        )
