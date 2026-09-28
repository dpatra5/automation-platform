from typing import List, Optional, Sequence
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.models.models import TestCase, TestRun, StatusEnum
from app.repositories.base import BaseRepository


class RunRepository(BaseRepository[TestRun]):
    """Repository for TestRun model operations."""

    def __init__(self, session: AsyncSession):
        super().__init__(TestRun, session)

    async def get_filtered(
        self,
        test_case_id: Optional[str] = None,
        status: Optional[StatusEnum] = None,
        project_id: Optional[str] = None,
    ) -> List[TestRun]:
        """Get test runs filtered by test case, project and/or status."""
        query = select(TestRun).order_by(TestRun.started_at.desc())
        if test_case_id:
            query = query.filter(TestRun.test_case_id == test_case_id)
        if project_id:
            query = query.join(TestCase, TestRun.test_case_id == TestCase.id).filter(
                TestCase.project_id == project_id
            )
        if status:
            query = query.filter(TestRun.status == status)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_many(self, ids: Sequence[str]) -> List[TestRun]:
        """The runs named by a set of ids, ignoring any that are already gone."""
        if not ids:
            return []
        result = await self.session.execute(
            select(TestRun).filter(TestRun.id.in_(list(ids)))
        )
        return list(result.scalars().all())

    async def get_with_details(self, id: str) -> TestRun | None:
        from sqlalchemy.orm import selectinload

        # populate_existing: the run was loaded before its steps ran, when it
        # had no results and no evidence, and the session keeps that instance
        # alive. Without this the eager loaders leave those empty collections
        # in place and the report says a finished run did nothing.
        result = await self.session.execute(
            select(TestRun)
            .options(
                selectinload(TestRun.step_results), selectinload(TestRun.evidences)
            )
            .filter(TestRun.id == id)
            .execution_options(populate_existing=True)
        )
        return result.scalars().first()
