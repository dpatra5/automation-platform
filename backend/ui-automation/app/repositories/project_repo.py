from sqlalchemy.ext.asyncio import AsyncSession
from app.models.models import Project
from app.repositories.base import BaseRepository

class ProjectRepository(BaseRepository[Project]):
    """Repository for Project model operations."""
    def __init__(self, session: AsyncSession):
        super().__init__(Project, session)
