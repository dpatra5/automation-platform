from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Evidence
from app.repositories.base import BaseRepository

class EvidenceRepository(BaseRepository[Evidence]):
    """Repository for Evidence model operations."""
    def __init__(self, session: AsyncSession):
        super().__init__(Evidence, session)
