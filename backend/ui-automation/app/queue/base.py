from abc import ABC, abstractmethod

class JobQueue(ABC):
    """Base interface for background job queues."""
    @abstractmethod
    async def enqueue(self, task_id: str, payload: dict) -> None:
        pass
