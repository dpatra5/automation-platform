import pytest
from app.repositories.base import BaseRepository
from app.repositories.run_repo import RunRepository
from app.models.models import (
    Project,
    StatusEnum,
    StepResult,
    TestCase,
    TestRun,
    Step,
    ActionEnum,
    SelectorStrategyEnum,
)


class ProjectRepository(BaseRepository[Project]):
    pass


class TestCaseRepository(BaseRepository[TestCase]):
    pass


@pytest.mark.asyncio
async def test_create_project(db_session):
    repo = ProjectRepository(Project, db_session)
    project = await repo.create(
        {"name": "Repo Test Project", "base_url": "https://repo.test"}
    )

    assert project.id is not None
    assert project.name == "Repo Test Project"
    assert project.base_url == "https://repo.test"


@pytest.mark.asyncio
async def test_get_project_by_id(db_session, project_factory):
    repo = ProjectRepository(Project, db_session)
    created_project = await project_factory(name="Get Me")

    project = await repo.get_by_id(created_project.id)
    assert project is not None
    assert project.name == "Get Me"


@pytest.mark.asyncio
async def test_list_projects(db_session, project_factory):
    repo = ProjectRepository(Project, db_session)
    await project_factory(name="Project 1")
    await project_factory(name="Project 2")

    projects = await repo.get_all()
    assert len(projects) >= 2
    names = [p.name for p in projects]
    assert "Project 1" in names
    assert "Project 2" in names


@pytest.mark.asyncio
async def test_create_test_case_with_steps(db_session, project_factory):
    project = await project_factory()
    tc_repo = TestCaseRepository(TestCase, db_session)

    tc = await tc_repo.create(
        {
            "project_id": project.id,
            "name": "TC with steps",
            "start_url": "https://example.com",
        }
    )

    step1 = Step(
        test_case_id=tc.id,
        order_index=1,
        action=ActionEnum.click,
        selector="btn",
        selector_strategy=SelectorStrategyEnum.css,
    )
    db_session.add(step1)
    await db_session.commit()

    assert tc.id is not None
    await db_session.refresh(tc, attribute_names=["steps"])
    assert len(tc.steps) == 1
    assert tc.steps[0].action == ActionEnum.click


@pytest.mark.asyncio
async def test_get_test_case_with_steps(db_session, test_case_factory):
    tc_repo = TestCaseRepository(TestCase, db_session)
    created_tc = await test_case_factory(name="Get TC")

    step1 = Step(
        test_case_id=created_tc.id,
        order_index=1,
        action=ActionEnum.navigate,
        selector="",
        selector_strategy=SelectorStrategyEnum.css,
        value="url",
    )
    db_session.add(step1)
    await db_session.commit()

    tc = await tc_repo.get_by_id(created_tc.id)
    await db_session.refresh(tc, attribute_names=["steps"])
    assert tc is not None
    assert len(tc.steps) == 1


@pytest.mark.asyncio
async def test_delete_test_case(db_session, test_case_factory):
    tc_repo = TestCaseRepository(TestCase, db_session)
    created_tc = await test_case_factory(name="Delete Me")

    tc = await tc_repo.get_by_id(created_tc.id)
    assert tc is not None

    await tc_repo.delete(tc)

    deleted_tc = await tc_repo.get_by_id(created_tc.id)
    assert deleted_tc is None


@pytest.mark.asyncio
async def test_a_finished_run_reports_the_results_written_while_it_ran(
    db_session, test_case_factory
):
    """The bug behind an empty report: a run read before it had any results.

    A run is loaded when it starts, when it has none, and the same session is
    still holding that instance when the report is built at the end. Nothing
    in between expires it, so the results written while it ran have to be read
    back over the top of the empty ones.
    """
    tc = await test_case_factory()
    run = TestRun(test_case_id=tc.id, status=StatusEnum.running)
    db_session.add(run)
    await db_session.commit()

    repo = RunRepository(db_session)
    started = await repo.get_by_id(run.id)
    assert started is not None and not started.step_results

    db_session.add(
        StepResult(test_run_id=run.id, status=StatusEnum.passed, duration_ms=12)
    )
    await db_session.commit()

    finished = await repo.get_with_details(run.id)
    assert finished is not None
    assert len(finished.step_results) == 1, "the report would have said 0 of 0 steps"
