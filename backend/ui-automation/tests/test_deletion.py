"""Deleting a project, and deleting runs under one.

A delete that leaves the evidence directory behind is a slow disk leak nobody
notices, and a delete that lands on a run still in flight leaves Chrome writing
files for something that no longer exists. Both are checked here.
"""

import pytest
import pytest_asyncio
from sqlalchemy import select

from app.exceptions import NotFoundError, RewindError
from app.models.models import (
    AuthProfile,
    Evidence,
    Project,
    StatusEnum,
    StepResult,
    TestCase,
    TestRun,
)
from app.repositories.auth_profile_repo import AuthProfileRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_repo import RunRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.services import artifacts
from app.services.project_service import ProjectService
from app.services.run_service import RunService


@pytest.fixture(autouse=True)
def artifacts_root(tmp_path, monkeypatch):
    """Point the evidence tree at a temporary directory for every test here."""
    monkeypatch.setattr(artifacts.settings, "artifacts_dir", str(tmp_path))
    return tmp_path


def evidence_dir(root, run_id: str):
    directory = root / run_id
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "failure.png").write_bytes(b"png")
    return directory


@pytest_asyncio.fixture
async def run_factory(db_session, test_case_factory):
    async def _create(test_case=None, status=StatusEnum.passed):
        test_case = test_case or await test_case_factory()
        run = TestRun(test_case_id=test_case.id, status=status)
        db_session.add(run)
        await db_session.commit()
        await db_session.refresh(run)
        return run

    return _create


@pytest.fixture
def run_service(db_session):
    return RunService(RunRepository(db_session), TestCaseRepository(db_session))


@pytest.fixture
def project_service(db_session):
    return ProjectService(
        ProjectRepository(db_session), AuthProfileRepository(db_session)
    )


# ------------------------------------------------------------------- runs


@pytest.mark.asyncio
async def test_deleting_a_run_takes_its_evidence_with_it(
    run_service, run_factory, artifacts_root
):
    run = await run_factory()
    directory = evidence_dir(artifacts_root, run.id)

    await run_service.delete_run(run.id)

    assert not directory.exists()
    with pytest.raises(NotFoundError):
        await run_service.get_run(run.id)


@pytest.mark.asyncio
async def test_a_run_still_going_is_not_deleted(run_service, run_factory):
    run = await run_factory(status=StatusEnum.running)

    with pytest.raises(RewindError):
        await run_service.delete_run(run.id)

    assert await run_service.run_repo.get_by_id(run.id) is not None


@pytest.mark.asyncio
async def test_deleting_several_runs_reports_what_went(
    run_service, run_factory, artifacts_root
):
    kept = await run_factory()
    gone = [await run_factory(), await run_factory()]
    directories = [evidence_dir(artifacts_root, run.id) for run in gone]

    # One id names nothing: another tab deleted it while this page was open.
    deleted = await run_service.delete_runs([r.id for r in gone] + ["not-a-run"])

    assert deleted == 2
    assert all(not d.exists() for d in directories)
    assert await run_service.run_repo.get_by_id(kept.id) is not None


@pytest.mark.asyncio
async def test_a_batch_delete_stops_if_any_run_is_still_going(run_service, run_factory):
    finished = await run_factory()
    live = await run_factory(status=StatusEnum.running)

    with pytest.raises(RewindError):
        await run_service.delete_runs([finished.id, live.id])

    assert await run_service.run_repo.get_by_id(finished.id) is not None


@pytest.mark.asyncio
async def test_runs_can_be_listed_for_a_project(
    run_service, run_factory, test_case_factory, project_factory
):
    mine = await test_case_factory(project=await project_factory(name="Mine"))
    theirs = await test_case_factory(project=await project_factory(name="Theirs"))
    wanted = await run_factory(test_case=mine)
    await run_factory(test_case=theirs)

    found = await run_service.get_runs(project_id=mine.project_id)

    assert [r.id for r in found] == [wanted.id]


@pytest.mark.asyncio
async def test_deleting_a_missing_run_says_so(run_service):
    with pytest.raises(NotFoundError):
        await run_service.delete_run("not-a-run")


# ---------------------------------------------------------------- projects


@pytest.mark.asyncio
async def test_deleting_a_project_clears_everything_under_it(
    project_service, project_factory, test_case_factory, db_session, artifacts_root
):
    project = await project_factory()
    test_case = await test_case_factory(project=project)
    run = TestRun(test_case_id=test_case.id, status=StatusEnum.passed)
    db_session.add(run)
    db_session.add(
        AuthProfile(project_id=project.id, name="session", storage_state_json="{}")
    )
    await db_session.commit()
    db_session.add(Evidence(test_run_id=run.id, type="screenshot", file_path="x.png"))
    await db_session.commit()
    directory = evidence_dir(artifacts_root, run.id)

    await project_service.delete_project(project.id)

    for model in (Project, TestCase, TestRun, Evidence, StepResult, AuthProfile):
        rows = (await db_session.execute(select(model))).scalars().all()
        assert rows == [], f"{model.__name__} rows survived the project"
    assert not directory.exists()


@pytest.mark.asyncio
async def test_deleting_a_project_leaves_other_projects_alone(
    project_service, project_factory, test_case_factory, db_session
):
    doomed = await project_factory(name="Doomed")
    kept = await project_factory(name="Kept")
    await test_case_factory(project=doomed)
    survivor = await test_case_factory(project=kept)

    await project_service.delete_project(doomed.id)

    remaining = (await db_session.execute(select(TestCase.id))).scalars().all()
    assert list(remaining) == [survivor.id]


@pytest.mark.asyncio
async def test_a_project_with_a_run_in_flight_is_not_deleted(
    project_service, project_factory, test_case_factory, db_session
):
    project = await project_factory()
    test_case = await test_case_factory(project=project)
    db_session.add(TestRun(test_case_id=test_case.id, status=StatusEnum.running))
    await db_session.commit()

    with pytest.raises(RewindError):
        await project_service.delete_project(project.id)

    assert await project_service.project_repo.get_by_id(project.id) is not None


@pytest.mark.asyncio
async def test_deleting_a_missing_project_says_so(project_service):
    with pytest.raises(NotFoundError):
        await project_service.delete_project("not-a-project")


# --------------------------------------------------------------- artifacts


def test_only_directories_inside_the_artifacts_tree_are_removed(
    artifacts_root, tmp_path
):
    """The one mistake here that cannot be undone is deleting the wrong tree."""
    outside = tmp_path.parent / "not-artifacts"
    outside.mkdir(exist_ok=True)

    assert artifacts.remove_run_artifacts("../not-artifacts") is False
    assert outside.exists()
