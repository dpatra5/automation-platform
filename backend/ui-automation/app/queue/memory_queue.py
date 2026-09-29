import asyncio
import structlog
from app.queue.base import JobQueue

logger = structlog.get_logger(__name__)

class MemoryQueue(JobQueue):
    """In-memory background job queue."""
    def __init__(self):
        self._queue = asyncio.Queue()

    async def enqueue(self, task_id: str, payload: dict) -> None:
        await self._queue.put({"task_id": task_id, "payload": payload})
        logger.info("enqueued_task", task_id=task_id)

    async def get(self) -> dict:
        return await self._queue.get()
        
    def task_done(self):
        self._queue.task_done()
