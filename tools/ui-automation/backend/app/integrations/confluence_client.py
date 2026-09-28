from app.integrations.base import DocStore
import structlog

logger = structlog.get_logger(__name__)


class ConfluenceClient(DocStore):
    """Confluence Document Store integration (stub)."""

    def __init__(self, host: str, token: str):
        self.host = host
        self.token = token

    async def publish_report(self, title: str, content: str) -> str:
        logger.info("confluence_publish", title=title)
        return "CONF-100"

    async def test_connection(self) -> bool:
        return bool(self.host and self.token)
