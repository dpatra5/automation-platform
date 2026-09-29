from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.models import AuthProfile
from app.repositories.base import BaseRepository
from typing import Optional

class AuthProfileRepository(BaseRepository[AuthProfile]):
    """Repository for AuthProfile operations."""
    def __init__(self, session: AsyncSession):
        super().__init__(AuthProfile, session)
        
    async def get_by_project_id(self, project_id: str) -> Optional[AuthProfile]:
        result = await self.session.execute(select(AuthProfile).filter(AuthProfile.project_id == project_id))
        return result.scalars().first()
