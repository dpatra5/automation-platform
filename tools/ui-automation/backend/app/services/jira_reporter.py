"""Pushing finished runs to Jira.

Reporting is a side effect of a run, never a condition of it: if Jira is down,
misconfigured or slow, the run keeps its own result and the failure is recorded
against it so the dashboard can say what went wrong.
"""

import logging
from pathlib import Path
from typing import Optional

from app.config import settings
from app.integrations.jira_client import JiraError, get_jira_client
from app.models.models import JiraSyncEnum
from app.services import reporting
from app.services.reporting import RunSummary

logger = logging.getLogger(__name__)


class JiraReporter:
    """Posts a comment, then attaches whatever evidence it can."""

    def __init__(self, client=None):
        # Resolved lazily so a missing configuration is simply "nothing to do".
        self._client = client if client is not None else get_jira_client()

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def report_run(
        self, issue_key: Optional[str], summary: RunSummary, project_name: str
    ) -> dict:
        if not issue_key:
            return _skipped("No Jira key on this project.")
        if not self.enabled:
            return _skipped("Jira is not configured on the backend.")

        body = reporting.jira_comment_for_run(summary, project_name)
        evidence = summary.evidence_paths() if settings.jira_attach_evidence else []
        return await self._publish(issue_key, body, evidence)

    async def report_batch(
        self,
        issue_key: Optional[str],
        summaries: list[RunSummary],
        project_name: str,
        batch_name: str,
        status: str,
        report_path: Optional[str] = None,
    ) -> dict:
        if not issue_key:
            return _skipped("No Jira key on this project.")
        if not self.enabled:
            return _skipped("Jira is not configured on the backend.")

        body = reporting.jira_comment_for_batch(
            batch_name, summaries, project_name, status
        )
        evidence: list[str] = []
        if settings.jira_attach_evidence:
            if report_path:
                evidence.append(str(Path(report_path).resolve()))
            evidence += reporting.collect_evidence_paths(summaries)
        return await self._publish(issue_key, body, evidence)

    async def _publish(self, issue_key: str, body: str, evidence: list[str]) -> dict:
        try:
            comment_id = await self._client.add_comment(issue_key, body)
        except JiraError as e:
            logger.warning("Jira comment on %s failed: %s", issue_key, e)
            return {
                "jira_issue_key": issue_key,
                "jira_status": JiraSyncEnum.failed,
                "jira_error": str(e),
            }
        except Exception as e:  # a bug here must not mark the run as broken
            logger.exception("Unexpected error commenting on %s", issue_key)
            return {
                "jira_issue_key": issue_key,
                "jira_status": JiraSyncEnum.failed,
                "jira_error": f"Unexpected error talking to Jira: {e}",
            }

        attach_error = ""
        if evidence:
            try:
                attached = await self._client.attach_files(issue_key, evidence)
                logger.info(
                    "Attached %d evidence files to %s", len(attached), issue_key
                )
            except JiraError as e:
                attach_error = (
                    f"Comment {comment_id} posted, but the evidence upload failed: {e}"
                )
                logger.warning(attach_error)
            except Exception as e:
                attach_error = (
                    f"Comment {comment_id} posted, but the evidence upload failed: {e}"
                )
                logger.exception("Unexpected error attaching evidence to %s", issue_key)

        return {
            "jira_issue_key": issue_key,
            # A posted comment is the point; a missing attachment is a warning.
            "jira_status": JiraSyncEnum.posted,
            "jira_error": attach_error or None,
        }


def _skipped(reason: str) -> dict:
    return {
        "jira_issue_key": None,
        "jira_status": JiraSyncEnum.skipped,
        "jira_error": reason,
    }
