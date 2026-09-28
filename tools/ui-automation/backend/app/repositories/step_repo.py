from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Step
from app.repositories.base import BaseRepository

class StepRepository(BaseRepository[Step]):
    """Repository for Step model operations."""
    def __init__(self, session: AsyncSession):
        super().__init__(Step, session)
