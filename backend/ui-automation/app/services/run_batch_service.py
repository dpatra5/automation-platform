"""Replaying several test cases one after another, reported as one result.

Sequential on purpose: the runs share a browser profile and a signed-in
session, and a suite that fires them in parallel would have them fighting over
the same application state. A leg that fails does not stop the batch - the
point of a consolidated report is to see everything that broke, not the first
thing.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import List, Optional

from app.exceptions import NotFoundError, RewindError
from app.models.models import RunBatch, StatusEnum
from app.repositories.auth_profile_repo import AuthProfileRepository
from app.repositories.project_repo import ProjectRepository
from app.repositories.run_batch_repo import RunBatchRepository
from app.repositories.run_repo import RunRepository
from app.repositories.test_case_repo import TestCaseRepository
from app.services import reporting
from app.services.jira_reporter import JiraReporter
from app.services.run_service import execute_run, track

logger = logging.getLogger(__name__)

MAX_BATCH_SIZE = 50


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class RunBatchService:
    """Creates a batch, then walks it in the background."""

    def __init__(
        self,
        batch_repo: RunBatchRepository,
        run_repo: RunRepository,
        tc_repo: TestCaseRepository,
        auth_repo: Optional[AuthProfileRepository] = None,
        project_repo: Optional[ProjectRepository] = None,
    ):
        self.batch_repo = batch_repo
        self.run_repo = run_repo
        self.tc_repo = tc_repo
        self.auth_repo = auth_repo
        self.project_repo = project_repo

    async def create_batch(
        self,
        test_case_ids: List[str],
        name: Optional[str] = None,
        trigger_source: str = "manual",
    ) -> RunBatch:
        """Queue the given test cases, in the order they were selected."""
        ordered = _dedupe(test_case_ids)
        if not ordered:
            raise RewindError("Select at least one test case to run.")
        if len(ordered) > MAX_BATCH_SIZE:
            raise RewindError(
                f"A sequence can hold at most {MAX_BATCH_SIZE} test cases; {len(ordered)} were selected."
            )

        test_cases = []
        for tc_id in ordered:
            tc = await self.tc_repo.get_with_steps(tc_id)
            if not tc:
                raise NotFoundError(f"Test case {tc_id} not found")
            test_cases.append(tc)

        project_ids = {tc.project_id for tc in test_cases}
        if len(project_ids) > 1:
            raise RewindError(
                "A sequence runs against one project at a time, so its report and its "
                "Jira update stay coherent. Select test cases from a single project."
            )
        project_id = test_cases[0].project_id

        # Loaded on the request session: the background task only ever reads
        # already-populated columns off these.
        project = (
            await self.project_repo.get_by_id(project_id) if self.project_repo else None
        )
        auth_profile = (
            await self.auth_repo.get_by_project_id(project_id)
            if self.auth_repo
            else None
        )

        batch = await self.batch_repo.create(
            {
                "project_id": project_id,
                "name": name or _default_name(test_cases),
                "status": StatusEnum.running,
                "trigger_source": trigger_source,
                "started_at": _utcnow(),
            }
        )

        runs = []
        for order, tc in enumerate(test_cases):
            runs.append(
                await self.run_repo.create(
                    {
                        "test_case_id": tc.id,
                        "status": StatusEnum.pending,
                        "trigger_source": f"{trigger_source} (sequence)",
                        "batch_id": batch.id,
                        "batch_order": order,
                    }
                )
            )

        legs = [(run.id, tc) for run, tc in zip(runs, test_cases)]
        track(asyncio.create_task(_walk_batch(batch.id, legs, auth_profile, project)))
        return batch

    async def get_batches(self, project_id: Optional[str] = None) -> List[RunBatch]:
        return await self.batch_repo.get_recent(project_id)

    async def get_batch(self, batch_id: str) -> RunBatch:
        batch = await self.batch_repo.get_with_runs(batch_id)
        if not batch:
            raise NotFoundError("Run sequence not found")
        return batch


async def _walk_batch(batch_id: str, legs, auth_profile, project) -> None:
    """Run every leg in order, then write the report and update Jira."""
    from app.db.session import AsyncSessionLocal

    summaries: list[reporting.RunSummary] = []
    for run_id, tc in legs:
        try:
            summary = await execute_run(run_id, tc, auth_profile, project)
        except Exception as e:
            # execute_run already records its own failures; this is the belt
            # that keeps one bad leg from abandoning the rest of the sequence.
            logger.exception("Leg %s of batch %s crashed: %s", run_id, batch_id, e)
            summary = None
        if summary:
            summaries.append(summary)

    try:
        async with AsyncSessionLocal() as session:
            repo = RunBatchRepository(session)
            batch = await repo.get_by_id(batch_id)
            if not batch:
                logger.error("Batch %s vanished while it was running", batch_id)
                return

            batch.status = reporting.overall_status(summaries)
            batch.finished_at = _utcnow()
            if not summaries:
                batch.error_message = "No run in this sequence produced a result."

            project_name = getattr(project, "name", "") or ""
            batch.report_path = reporting.write_batch_report(
                batch, summaries, project_name
            )
            await session.commit()

            outcome = await JiraReporter().report_batch(
                issue_key=getattr(project, "jira_key", None),
                summaries=summaries,
                project_name=project_name,
                batch_name=batch.name,
                status=batch.status.value,
                report_path=batch.report_path,
            )
            for key, value in outcome.items():
                setattr(batch, key, value)
            await session.commit()
            logger.info("Batch %s finished: %s", batch_id, batch.status)
    except Exception as e:
        logger.exception("Could not close out batch %s: %s", batch_id, e)


def _dedupe(ids: List[str]) -> List[str]:
    """Keep the selection order, drop repeats."""
    seen: set[str] = set()
    return [i for i in ids if i and not (i in seen or seen.add(i))]


def _default_name(test_cases) -> str:
    stamp = _utcnow().strftime("%Y-%m-%d %H:%M")
    return f"{len(test_cases)} test case{'' if len(test_cases) == 1 else 's'} · {stamp}"
