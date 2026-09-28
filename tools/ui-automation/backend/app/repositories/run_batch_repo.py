import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import RunBatch
from app.repositories.base import BaseRepository


logger = logging.getLogger(__name__)


class RunBatchRepository(BaseRepository[RunBatch]):
    """Repository for sequential run batches."""

    def __init__(self, session: AsyncSession):
        super().__init__(RunBatch, session)

    async def get_recent(
        self, project_id: Optional[str] = None, limit: int = 50
    ) -> List[RunBatch]:
        query = select(RunBatch).order_by(RunBatch.started_at.desc()).limit(limit)
        if project_id:
            query = query.filter(RunBatch.project_id == project_id)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_with_runs(self, id: str) -> RunBatch | None:
        result = await self.session.execute(
            select(RunBatch)
            .options(selectinload(RunBatch.runs))
            .filter(RunBatch.id == id)
        )
        return result.scalars().first()
