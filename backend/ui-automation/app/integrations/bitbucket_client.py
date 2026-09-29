from typing import Any, Optional, Sequence

from app.integrations.base import IssueTracker
import structlog

logger = structlog.get_logger(__name__)


class BitbucketClient(IssueTracker):
    """Bitbucket Client integration (stub)."""

    def __init__(self, host: str, token: str):
        self.host = host
        self.token = token

    async def create_issue(self, title: str, description: str) -> str:
        logger.info("bitbucket_create_issue", title=title)
        return "BB-100"

    async def get_issue(self, issue_key: str) -> Optional[dict[str, Any]]:
        logger.info("bitbucket_get_issue", issue_key=issue_key)
        return None

    async def add_comment(self, issue_key: str, body: str) -> str:
        logger.info("bitbucket_add_comment", issue_key=issue_key)
        return "bb-comment-1"

    async def attach_files(self, issue_key: str, paths: Sequence[str]) -> list[str]:
        logger.info("bitbucket_attach_files", issue_key=issue_key)
        return []

    async def test_connection(self) -> bool:
        return bool(self.host and self.token)
