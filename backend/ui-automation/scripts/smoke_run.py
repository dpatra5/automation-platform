"""End-to-end smoke check for the regression runner.

Runs a real browser against a throwaway database and asserts that:
  * a recorded flow is traversed and evidence is captured,
  * the wider action set (check, dblclick, waits, assertions...) replays,
  * exit criteria run after every recorded step and decide the verdict,
  * several test cases replay in sequence and produce one consolidated report,
  * step results land while the run is still going, not only at the end,
  * a broken step fails the run instead of crashing it,
  * an expired saved session stops the run before the browser opens.

Deliberately runs on a SelectorEventLoop: that is what `uvicorn --reload`
serves on, and it is where Playwright's driver subprocess used to die with
NotImplementedError.

    python -m scripts.smoke_run
"""

import asyncio
import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

WORKDIR = Path(tempfile.mkdtemp(prefix="rewind-smoke-"))
os.environ["DATABASE_URL"] = f"sqlite+aiosqlite:///{(WORKDIR / 'smoke.db').as_posix()}"
os.environ["ARTIFACTS_DIR"] = str(WORKDIR / "artifacts")
os.environ.setdefault("HEADLESS", "true")
os.environ.setdefault("SLOW_MO_MS", "0")
os.environ.setdefault("STEP_TIMEOUT_MS", "6000")

from app.db.session import AsyncSessionLocal, engine  # noqa: E402
from app.models.base import Base  # noqa: E402
from app.models.models import (  # noqa: E402
    ActionEnum,
    AuthProfile,
    Project,
    SelectorStrategyEnum,
    StatusEnum,
    Step,
    TestCase,
)
from app.repositories.auth_profile_repo import AuthProfileRepository  # noqa: E402
from app.repositories.project_repo import ProjectRepository  # noqa: E402
from app.repositories.run_batch_repo import RunBatchRepository  # noqa: E402
from app.repositories.run_repo import RunRepository  # noqa: E402
from app.repositories.test_case_repo import TestCaseRepository  # noqa: E402
from app.services.run_batch_service import RunBatchService  # noqa: E402
from app.services.run_service import RunService  # noqa: E402

START_URL = "https://demo.playwright.dev/todomvc/#/"
CSS = SelectorStrategyEnum.css


def step(tc_id, index, action, selector="", value=None, **extra):
    return Step(
        test_case_id=tc_id,
        order_index=index,
        action=action,
        selector=selector,
        selector_strategy=CSS,
        value=value,
        **extra,
    )


async def seed() -> dict:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as session:
        project = Project(name="Smoke", base_url=START_URL)
        session.add(project)
        await session.commit()

        basic = TestCase(project_id=project.id, name="basic", start_url=START_URL)
        rich = TestCase(project_id=project.id, name="rich actions", start_url=START_URL)
        broken = TestCase(project_id=project.id, name="broken", start_url=START_URL)
        criteria = TestCase(
            project_id=project.id, name="exit criteria", start_url=START_URL
        )
        session.add_all([basic, rich, broken, criteria])
        await session.commit()

        session.add_all(
            [
                step(basic.id, 1, ActionEnum.fill, ".new-todo", "Buy milk"),
                step(basic.id, 2, ActionEnum.press_key, ".new-todo", "Enter"),
                step(basic.id, 3, ActionEnum.click, ".toggle"),
            ]
        )

        # Every action group the recorder can emit, on a page that supports them.
        session.add_all(
            [
                step(rich.id, 1, ActionEnum.fill, ".new-todo", "write tests"),
                step(rich.id, 2, ActionEnum.press_key, ".new-todo", "Enter"),
                step(rich.id, 3, ActionEnum.type, ".new-todo", "ship it"),
                step(rich.id, 4, ActionEnum.press_key, ".new-todo", "Enter"),
                step(
                    rich.id,
                    5,
                    ActionEnum.wait_for_selector,
                    ".todo-list li:nth-child(2)",
                ),
                step(
                    rich.id, 6, ActionEnum.check, ".todo-list li:nth-child(1) .toggle"
                ),
                step(
                    rich.id,
                    7,
                    ActionEnum.assert_,
                    ".todo-count",
                    assertion_type="text_contains",
                    expected_value="1 item left",
                ),
                step(rich.id, 8, ActionEnum.hover, ".todo-list li:nth-child(2)"),
                step(
                    rich.id, 9, ActionEnum.dblclick, ".todo-list li:nth-child(2) label"
                ),
                step(
                    rich.id,
                    10,
                    ActionEnum.press_key,
                    ".todo-list li:nth-child(2) .edit",
                    "Escape",
                ),
                step(rich.id, 11, ActionEnum.click, ".filters li:nth-child(2) a"),
                step(
                    rich.id,
                    12,
                    ActionEnum.assert_,
                    "",
                    assertion_type="url_contains",
                    expected_value="active",
                ),
                step(rich.id, 13, ActionEnum.wait, "", "200"),
                step(rich.id, 14, ActionEnum.uncheck, ".toggle-all"),
                step(rich.id, 15, ActionEnum.reload),
            ]
        )

        session.add_all(
            [
                step(broken.id, 1, ActionEnum.click, ".this-element-does-not-exist"),
            ]
        )

        # Exit criteria carry order_index 0 and 1 but must still run last.
        session.add_all(
            [
                step(criteria.id, 1, ActionEnum.fill, ".new-todo", "pay the invoice"),
                step(criteria.id, 2, ActionEnum.press_key, ".new-todo", "Enter"),
                step(
                    criteria.id,
                    0,
                    ActionEnum.assert_,
                    ".todo-list li",
                    assertion_type="count_equals",
                    expected_value="1",
                    is_exit_criteria=True,
                ),
                step(
                    criteria.id,
                    1,
                    ActionEnum.assert_,
                    ".todo-list li label",
                    assertion_type="text_equals",
                    expected_value="pay the invoice",
                    is_exit_criteria=True,
                ),
            ]
        )
        await session.commit()
        return {
            "project": project.id,
            "basic": basic.id,
            "rich": rich.id,
            "broken": broken.id,
            "criteria": criteria.id,
        }


async def save_session(project_id: str, expires_at: datetime) -> None:
    state = json.dumps({"cookies": [], "origins": []})
    async with AsyncSessionLocal() as session:
        repo = AuthProfileRepository(session)
        existing = await repo.get_by_project_id(project_id)
        data = {"name": "smoke", "storage_state_json": state, "expires_at": expires_at}
        if existing:
            await repo.update(existing, data)
        else:
            await repo.create({"project_id": project_id, **data})


async def run_case(test_case_id: str, watch_live: bool = False):
    """Trigger a run and wait for the background task to persist its results."""
    async with AsyncSessionLocal() as session:
        service = RunService(
            RunRepository(session),
            TestCaseRepository(session),
            AuthProfileRepository(session),
        )
        run_id = (await service.trigger_run(test_case_id)).id

    saw_partial = False
    for _ in range(150):
        await asyncio.sleep(0.7)
        async with AsyncSessionLocal() as session:
            current = await RunRepository(session).get_with_details(run_id)
            if current.status == StatusEnum.running and current.step_results:
                saw_partial = True
            if current.status != StatusEnum.running:
                if watch_live and not saw_partial:
                    raise AssertionError(
                        "No step results appeared while the run was still going - "
                        "live progress is broken"
                    )
                return current
    raise AssertionError(f"Run {run_id} never finished")


async def run_sequence(test_case_ids: list[str]):
    """Queue a batch and wait for the consolidated report to be written."""
    async with AsyncSessionLocal() as session:
        service = RunBatchService(
            RunBatchRepository(session),
            RunRepository(session),
            TestCaseRepository(session),
            AuthProfileRepository(session),
            ProjectRepository(session),
        )
        batch_id = (await service.create_batch(test_case_ids, name="smoke sequence")).id

    for _ in range(300):
        await asyncio.sleep(0.7)
        async with AsyncSessionLocal() as session:
            current = await RunBatchRepository(session).get_with_runs(batch_id)
            if current and current.status not in (
                StatusEnum.running,
                StatusEnum.pending,
            ):
                return current
    raise AssertionError(f"Batch {batch_id} never finished")


async def main() -> None:
    ids = await seed()
    artifacts = Path(os.environ["ARTIFACTS_DIR"])

    # 1. A plain flow passes and captures everything.
    passed = await run_case(ids["basic"])
    assert passed.status == StatusEnum.passed, (
        f"expected pass, got {passed.status}: {passed.error_message}"
    )
    assert len(passed.step_results) == 3, (
        f"expected 3 step results, got {len(passed.step_results)}"
    )
    assert all(sr.screenshot_path for sr in passed.step_results), (
        "step screenshots missing"
    )
    kinds = {ev.type.value for ev in passed.evidences}
    assert {"console_log", "network_log", "video", "trace"} <= kinds, (
        f"missing evidence: {kinds}"
    )
    console = (artifacts / passed.id / "console.log").read_text(encoding="utf-8")
    assert "STEP" in console and "NAVIGATE" in console, (
        "console log was not really captured"
    )

    # 2. The wider action set replays, and results land while the run is live.
    rich = await run_case(ids["rich"], watch_live=True)
    assert rich.status == StatusEnum.passed, (
        f"rich actions failed: {rich.error_message}"
    )
    assert len(rich.step_results) == 15, (
        f"expected 15 step results, got {len(rich.step_results)}"
    )

    # 3. Exit criteria are evaluated after the flow, whatever their order_index.
    checked = await run_case(ids["criteria"])
    assert checked.status == StatusEnum.passed, (
        f"exit criteria failed: {checked.error_message}"
    )
    assert len(checked.step_results) == 4, (
        f"expected 4 step results, got {len(checked.step_results)}"
    )
    console = (artifacts / checked.id / "console.log").read_text(encoding="utf-8")
    assert console.index("STEP") < console.index("EXIT"), (
        "exit criteria ran before the flow"
    )

    # 4. A broken selector fails the run, with a failure screenshot.
    failed = await run_case(ids["broken"])
    assert failed.status == StatusEnum.failed, f"expected failure, got {failed.status}"
    assert failed.error_message, "failed run recorded no error message"
    assert any(ev.file_path.endswith("failure.png") for ev in failed.evidences), (
        "no failure screenshot"
    )

    # 5. Several test cases replay in order and produce one consolidated report.
    batch = await run_sequence([ids["basic"], ids["criteria"], ids["broken"]])
    assert len(batch.runs) == 3, (
        f"expected 3 runs in the sequence, got {len(batch.runs)}"
    )
    assert [r.batch_order for r in batch.runs] == [0, 1, 2], "sequence ran out of order"
    assert batch.status == StatusEnum.failed, (
        f"a sequence with a failing leg must fail: {batch.status}"
    )
    assert batch.report_path, "no consolidated report was written"
    report = (WORKDIR / batch.report_path).read_text(encoding="utf-8")
    assert "exit criteria" in report and "basic" in report, (
        "the report is missing its runs"
    )

    # 6. A live session is accepted...
    await save_session(ids["project"], datetime.now(timezone.utc) + timedelta(days=1))
    with_auth = await run_case(ids["basic"])
    assert with_auth.status == StatusEnum.passed, (
        f"run with a session failed: {with_auth.error_message}"
    )

    # ...and an expired one stops the run before the browser is opened.
    await save_session(ids["project"], datetime.now(timezone.utc) - timedelta(hours=1))
    expired = await run_case(ids["basic"])
    assert expired.status == StatusEnum.error, f"expected error, got {expired.status}"
    assert "expired" in (expired.error_message or "").lower(), expired.error_message
    assert not expired.step_results, "an expired session must not open the browser"

    print(
        f"OK - basic {passed.id}, rich {rich.id}, criteria {checked.id}, failed {failed.id}, "
        f"sequence {batch.id}, auth {with_auth.id}, expired {expired.id}\nartifacts in {WORKDIR}"
    )


if __name__ == "__main__":
    # SelectorEventLoop is what `uvicorn --reload` serves on; run there on
    # purpose so this check fails if the runner ever loses its own loop again.
    asyncio.run(main(), loop_factory=asyncio.SelectorEventLoop)
