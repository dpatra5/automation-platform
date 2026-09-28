from abc import ABC, abstractmethod
from typing import Any, Optional, Sequence


class IssueTracker(ABC):
    """Abstract interface for Issue Trackers."""

    @abstractmethod
    async def create_issue(self, title: str, description: str) -> str: ...

    @abstractmethod
    async def get_issue(self, issue_key: str) -> Optional[dict[str, Any]]:
        """The issue, or None when the tracker has no such key."""

    @abstractmethod
    async def add_comment(self, issue_key: str, body: str) -> str:
        """Post a comment and return its id."""

    @abstractmethod
    async def attach_files(self, issue_key: str, paths: Sequence[str]) -> list[str]:
        """Attach files to the issue and return the names that made it."""

    @abstractmethod
    async def test_connection(self) -> bool:
        """Whether the configured credentials can reach the tracker."""


class DocStore(ABC):
    """Abstract interface for Document Stores."""

    @abstractmethod
    async def publish_report(self, title: str, content: str) -> str: ...
