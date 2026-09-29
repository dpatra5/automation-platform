from typing import Any, Optional, Sequence

from app.integrations.base import IssueTracker, DocStore
import structlog

logger = structlog.get_logger(__name__)


class NoopIssueTracker(IssueTracker):
    """Stands in when no tracker is configured, so nothing has to branch on it."""

    async def create_issue(self, title: str, description: str) -> str:
        logger.info("noop_create_issue", title=title)
        return "NOOP-1"

    async def get_issue(self, issue_key: str) -> Optional[dict[str, Any]]:
        logger.info("noop_get_issue", issue_key=issue_key)
        return None

    async def add_comment(self, issue_key: str, body: str) -> str:
        logger.info("noop_add_comment", issue_key=issue_key)
        return "noop-comment-1"

    async def attach_files(self, issue_key: str, paths: Sequence[str]) -> list[str]:
        logger.info("noop_attach_files", issue_key=issue_key, count=len(list(paths)))
        return []

    async def test_connection(self) -> bool:
        return True


class NoopDocStore(DocStore):
    """No-op Doc Store."""

    async def publish_report(self, title: str, content: str) -> str:
        logger.info("noop_publish_report", title=title)
        return "noop-doc-1"
