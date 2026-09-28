from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from app.models.models import TestCase
from app.repositories.base import BaseRepository

class TestCaseRepository(BaseRepository[TestCase]):
    """Repository for TestCase model operations."""
    def __init__(self, session: AsyncSession):
        super().__init__(TestCase, session)

    async def get_by_project_id(self, project_id: str) -> List[TestCase]:
        """Get test cases for a given project."""
        result = await self.session.execute(
            select(TestCase).options(selectinload(TestCase.steps)).filter(TestCase.project_id == project_id)
        )
        return list(result.scalars().all())

    async def get_with_steps(self, id: str) -> TestCase | None:
        """Get a test case along with its steps."""
        result = await self.session.execute(
            select(TestCase).options(selectinload(TestCase.steps)).filter(TestCase.id == id)
        )
        return result.scalars().first()
