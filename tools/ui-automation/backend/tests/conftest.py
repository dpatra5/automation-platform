import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from unittest.mock import AsyncMock
from app.models.base import Base
from app.models.models import Project, TestCase, Step, TestRun

TEST_DB_URL = "sqlite+aiosqlite:///:memory:"

@pytest_asyncio.fixture(scope="function")
async def engine():
    engine = create_async_engine(TEST_DB_URL, echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield engine
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()

@pytest_asyncio.fixture(scope="function")
async def db_session(engine):
    AsyncSessionLocal = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )
    async with AsyncSessionLocal() as session:
        yield session

from unittest.mock import AsyncMock, MagicMock

@pytest.fixture
def mock_page():
    page = MagicMock()
    page.goto = AsyncMock()
    page.wait_for_timeout = AsyncMock()
    page.keyboard = MagicMock()
    page.keyboard.press = AsyncMock()

    locator_mock = AsyncMock()
    # Handlers act on `.first`; with a single match that is the locator itself.
    locator_mock.first = locator_mock
    locator_mock.count = AsyncMock(return_value=1)
    page.get_by_test_id.return_value = locator_mock
    page.get_by_role.return_value = locator_mock
    page.get_by_text.return_value = locator_mock
    page.locator.return_value = locator_mock
    page.locator_mock = locator_mock
    return page

@pytest_asyncio.fixture
async def project_factory(db_session):
    async def _create_project(name="Test Project", base_url="https://example.com"):
        project = Project(name=name, base_url=base_url)
        db_session.add(project)
        await db_session.commit()
        await db_session.refresh(project)
        return project
    return _create_project

@pytest_asyncio.fixture
async def test_case_factory(db_session, project_factory):
    async def _create_test_case(project=None, name="Test Case", start_url="https://example.com"):
        if not project:
            project = await project_factory()
        tc = TestCase(project_id=project.id, name=name, start_url=start_url)
        db_session.add(tc)
        await db_session.commit()
        await db_session.refresh(tc)
        return tc
    return _create_test_case
