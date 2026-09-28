import asyncio
import logging
import queue
from typing import List, Optional
from datetime import datetime, timezone
from app.models.models import TestRun, StatusEnum, StepResult, Evidence
from app.repositories.run_repo import RunRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.repositories.auth_profile_repo import AuthProfileRepository
from app.repositories.project_repo import ProjectRepository
from app.services.jira_reporter import JiraReporter
from app.services.reporting import RunSummary, summarise_run
from app.services.artifacts import remove_run_artifacts
from app.exceptions import NotFoundError, RewindError

logger = logging.getLogger(__name__)

# asyncio only holds a weak reference to running tasks; without this the
# background run can be garbage collected mid-flight.
_background_tasks: set[asyncio.Task] = set()

# How often the API session picks up step results from the runner thread.
PROGRESS_POLL_SECONDS = 0.5


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def track(task: asyncio.Task) -> asyncio.Task:
    """Keep a fire-and-forget task alive until it finishes."""
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return task


async def _drain_progress(progress: queue.Queue, session, run_id: str) -> None:
    """Persist step results the runner thread has finished, as they land."""
    added = False
    while True:
        try:
            sr_data = progress.get_nowait()
        except queue.Empty:
            break
        session.add(
            StepResult(
                test_run_id=run_id,
                step_id=sr_data["step_id"],
                status=sr_data["status"],
                duration_ms=sr_data.get("duration_ms", 0),
                screenshot_path=sr_data.get("screenshot_path"),
                error_message=sr_data.get("error_message"),
            )
        )
        added = True
    if added:
        await session.commit()


async def execute_run(
    run_id: str, tc, auth_profile=None, project=None, silent_mode: bool = False
) -> Optional[RunSummary]:
    """Drive one run to completion on its own DB session, then report it.

    Shared by a single replay and by every leg of a sequential batch, so both
    capture evidence, persist progress and reach Jira the same way. Returns the
    summary the consolidated report is built from.
    """
    from app.db.session import AsyncSessionLocal
    from app.execution.auth_manager import AuthManager
    from app.execution.runner import PlaywrightRunner, execute_blocking

    auth = AuthManager(auth_profile)
    try:
        async with AsyncSessionLocal() as session:
            repo = RunRepository(session)
            current_run = await repo.get_by_id(run_id)
            if not current_run:
                logger.error(f"Run {run_id} not found in background task")
                return None

            current_run.status = StatusEnum.running
            current_run.started_at = current_run.started_at or _utcnow()
            await session.commit()

            # Raises AuthExpiredError rather than replaying a dead session.
            auth_state_path = auth.get_storage_state_path(run_id)

            # The runner thread cannot touch the DB, so it hands finished
            # steps over a queue and this coroutine writes them. That is
            # what makes the dashboard timeline fill in while Chrome runs.
            progress: queue.Queue = queue.Queue()
            runner = PlaywrightRunner(
                current_run, tc, auth_state_path, on_step=progress.put, silent_mode=silent_mode
            )

            work = asyncio.create_task(asyncio.to_thread(execute_blocking, runner))
            while not work.done():
                await asyncio.sleep(PROGRESS_POLL_SECONDS)
                await _drain_progress(progress, session, run_id)
            result = await work
            await _drain_progress(progress, session, run_id)

            current_run.status = result["status"]
            current_run.error_message = result.get("error_message")
            current_run.finished_at = result.get("finished_at", _utcnow())

            for ev_data in result.get("evidences", []):
                session.add(
                    Evidence(
                        test_run_id=run_id,
                        type=ev_data["type"],
                        file_path=ev_data["file_path"],
                    )
                )

            await session.commit()
            logger.info(f"Run {run_id} completed with status: {result['status']}")
            return await _finish(session, run_id, tc, project)

    except Exception as e:
        logger.error(f"Run {run_id} failed with error: {e}", exc_info=True)
        try:
            async with AsyncSessionLocal() as session:
                repo = RunRepository(session)
                current_run = await repo.get_by_id(run_id)
                if current_run:
                    current_run.status = StatusEnum.error
                    current_run.error_message = str(e)
                    current_run.finished_at = _utcnow()
                    await session.commit()
                    return await _finish(session, run_id, tc, project)
        except Exception as inner_e:
            logger.error(f"Failed to update run {run_id} after error: {inner_e}")
        return None
    finally:
        auth.cleanup()


async def _finish(session, run_id: str, tc, project) -> Optional[RunSummary]:
    """Summarise the finished run and, when a Jira key is set, comment on it."""
    detailed = await RunRepository(session).get_with_details(run_id)
    if not detailed:
        return None
    summary = summarise_run(detailed, tc)

    # A run inside a batch is reported by the batch, so the issue gets one
    # consolidated comment instead of one per test case.
    if project is not None and detailed.batch_id is None:
        outcome = await JiraReporter().report_run(
            getattr(project, "jira_key", None),
            summary,
            getattr(project, "name", "") or "",
        )
        for key, value in outcome.items():
            setattr(detailed, key, value)
        await session.commit()

    return summary


class RunService:
    """Service for handling test runs."""

    def __init__(
        self,
        run_repo: RunRepository,
        tc_repo: TestCaseRepository,
        auth_repo: Optional[AuthProfileRepository] = None,
        project_repo: Optional[ProjectRepository] = None,
    ):
        self.run_repo = run_repo
        self.tc_repo = tc_repo
        self.auth_repo = auth_repo
        self.project_repo = project_repo

    async def trigger_run(
        self, test_case_id: str, trigger_source: str = "manual", silent_mode: bool = False
    ) -> TestRun:
        """Trigger a new test run for a test case."""
        tc = await self.tc_repo.get_with_steps(test_case_id)
        if not tc:
            raise NotFoundError("Test case not found")

        # Loaded here, on the request session, so the background task never
        # touches a closed session.
        auth_profile = None
        if self.auth_repo:
            auth_profile = await self.auth_repo.get_by_project_id(tc.project_id)
        project = (
            await self.project_repo.get_by_id(tc.project_id)
            if self.project_repo
            else None
        )

        run = await self.run_repo.create(
            {
                "test_case_id": test_case_id,
                "status": StatusEnum.running,
                "trigger_source": trigger_source,
                "started_at": _utcnow(),
            }
        )

        track(asyncio.create_task(execute_run(run.id, tc, auth_profile, project, silent_mode)))
        return run

    async def get_runs(
        self,
        test_case_id: Optional[str] = None,
        status: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> List[TestRun]:
        """Get filtered runs."""
        # Convert string status to enum for DB query
        status_enum = None
        if status:
            try:
                status_enum = StatusEnum(status)
            except ValueError:
                pass
        return await self.run_repo.get_filtered(test_case_id, status_enum, project_id)

    async def get_run(self, run_id: str) -> TestRun:
        """Get a single run."""
        run = await self.run_repo.get_with_details(run_id)
        if not run:
            raise NotFoundError("Run not found")
        return run

    async def delete_run(self, run_id: str) -> None:
        """Delete one run, and the evidence it wrote to disk with it."""
        run = await self.run_repo.get_by_id(run_id)
        if not run:
            raise NotFoundError("Run not found")
        if run.status == StatusEnum.running:
            raise RewindError(
                "This run is still going. Wait for it to finish before deleting it."
            )
        await self.run_repo.delete(run)
        remove_run_artifacts(run_id)

    async def delete_runs(self, run_ids: List[str]) -> int:
        """Delete several runs at once, and report how many actually went.

        Ids that name nothing are skipped rather than failing the request: the
        list came from a page that may have been open while another tab
        deleted something, and refusing the whole batch for that helps nobody.
        A run still in flight is refused, because deleting it would leave
        Chrome writing evidence for a run that no longer exists.
        """
        runs = await self.run_repo.get_many(run_ids)
        live = [r for r in runs if r.status == StatusEnum.running]
        if live:
            raise RewindError(
                f"{len(live)} of the selected runs are still going. "
                "Wait for them to finish before deleting them."
            )
        for run in runs:
            await self.run_repo.delete(run)
        for run in runs:
            remove_run_artifacts(run.id)
        return len(runs)
