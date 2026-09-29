from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.repositories.project_repo import ProjectRepository
from app.repositories.auth_profile_repo import AuthProfileRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.step_repo import StepRepository
from app.repositories.run_repo import RunRepository
from app.repositories.run_batch_repo import RunBatchRepository
from app.services.project_service import ProjectService
from app.services.test_case_service import TestCaseService
from app.services.run_service import RunService
from app.services.run_batch_service import RunBatchService
from app.services.recording_service import RecordingService


def get_project_repo(db: AsyncSession = Depends(get_db)) -> ProjectRepository:
    return ProjectRepository(db)


def get_auth_profile_repo(db: AsyncSession = Depends(get_db)) -> AuthProfileRepository:
    return AuthProfileRepository(db)


def get_project_service(
    project_repo: ProjectRepository = Depends(get_project_repo),
    auth_repo: AuthProfileRepository = Depends(get_auth_profile_repo),
) -> ProjectService:
    return ProjectService(project_repo, auth_repo)


def get_test_case_repo(db: AsyncSession = Depends(get_db)) -> TestCaseRepository:
    return TestCaseRepository(db)


def get_step_repo(db: AsyncSession = Depends(get_db)) -> StepRepository:
    return StepRepository(db)


def get_test_case_service(
    tc_repo: TestCaseRepository = Depends(get_test_case_repo),
    step_repo: StepRepository = Depends(get_step_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
) -> TestCaseService:
    return TestCaseService(tc_repo, step_repo, project_repo)


def get_run_repo(db: AsyncSession = Depends(get_db)) -> RunRepository:
    return RunRepository(db)


def get_run_batch_repo(db: AsyncSession = Depends(get_db)) -> RunBatchRepository:
    return RunBatchRepository(db)


def get_run_service(
    run_repo: RunRepository = Depends(get_run_repo),
    tc_repo: TestCaseRepository = Depends(get_test_case_repo),
    auth_repo: AuthProfileRepository = Depends(get_auth_profile_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
) -> RunService:
    return RunService(run_repo, tc_repo, auth_repo, project_repo)


def get_run_batch_service(
    batch_repo: RunBatchRepository = Depends(get_run_batch_repo),
    run_repo: RunRepository = Depends(get_run_repo),
    tc_repo: TestCaseRepository = Depends(get_test_case_repo),
    auth_repo: AuthProfileRepository = Depends(get_auth_profile_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
) -> RunBatchService:
    return RunBatchService(batch_repo, run_repo, tc_repo, auth_repo, project_repo)


def get_recording_service(
    tc_repo: TestCaseRepository = Depends(get_test_case_repo),
    step_repo: StepRepository = Depends(get_step_repo),
    project_repo: ProjectRepository = Depends(get_project_repo),
    auth_repo: AuthProfileRepository = Depends(get_auth_profile_repo),
) -> RecordingService:
    return RecordingService(tc_repo, step_repo, project_repo, auth_repo)
