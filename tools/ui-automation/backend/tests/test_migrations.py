"""An older database has to keep working after an upgrade.

`create_all` never touches a table that already exists, so anything the models
gained since a database was made has to be applied by hand. These build the old
shape on purpose and check the upgrade repairs it without losing rows.
"""

import pytest
import pytest_asyncio
from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import create_async_engine

import app.models.models  # noqa: F401  registers the tables on Base.metadata
from app.db.migrations import upgrade_schema

# The schema as it was before `ondelete` and the later columns arrived: no
# delete rules, and no is_exit_criteria / frame_url on a step.
LEGACY_SCHEMA = [
    """CREATE TABLE projects (
        id VARCHAR NOT NULL PRIMARY KEY, name VARCHAR NOT NULL,
        base_url VARCHAR NOT NULL, description VARCHAR, created_at DATETIME
    )""",
    """CREATE TABLE test_cases (
        id VARCHAR NOT NULL PRIMARY KEY, project_id VARCHAR,
        name VARCHAR NOT NULL, start_url VARCHAR NOT NULL, description VARCHAR,
        created_at DATETIME, updated_at DATETIME,
        FOREIGN KEY(project_id) REFERENCES projects (id)
    )""",
    """CREATE TABLE steps (
        id VARCHAR NOT NULL PRIMARY KEY, test_case_id VARCHAR,
        order_index INTEGER NOT NULL, action VARCHAR(9) NOT NULL,
        selector VARCHAR NOT NULL, selector_strategy VARCHAR(7) NOT NULL,
        value VARCHAR, assertion_type VARCHAR, expected_value VARCHAR,
        FOREIGN KEY(test_case_id) REFERENCES test_cases (id)
    )""",
    """CREATE TABLE test_runs (
        id VARCHAR NOT NULL PRIMARY KEY, test_case_id VARCHAR,
        status VARCHAR(7), started_at DATETIME, finished_at DATETIME,
        trigger_source VARCHAR, error_message VARCHAR,
        FOREIGN KEY(test_case_id) REFERENCES test_cases (id)
    )""",
    """CREATE TABLE step_results (
        id VARCHAR NOT NULL PRIMARY KEY, test_run_id VARCHAR, step_id VARCHAR,
        status VARCHAR(7) NOT NULL, duration_ms INTEGER NOT NULL,
        screenshot_path VARCHAR, error_message VARCHAR,
        FOREIGN KEY(test_run_id) REFERENCES test_runs (id),
        FOREIGN KEY(step_id) REFERENCES steps (id)
    )""",
    """CREATE TABLE evidences (
        id VARCHAR NOT NULL PRIMARY KEY, test_run_id VARCHAR,
        type VARCHAR(11) NOT NULL, file_path VARCHAR NOT NULL,
        created_at DATETIME,
        FOREIGN KEY(test_run_id) REFERENCES test_runs (id)
    )""",
]

SEED = [
    "INSERT INTO projects (id, name, base_url) VALUES ('p1', 'Demo', 'https://x')",
    """INSERT INTO test_cases (id, project_id, name, start_url)
       VALUES ('t1', 'p1', 'Case', 'https://x/start')""",
    """INSERT INTO test_cases (id, project_id, name, start_url)
       VALUES ('t2', 'p1', 'Kept', 'https://x/other')""",
    """INSERT INTO steps (id, test_case_id, order_index, action, selector,
       selector_strategy) VALUES ('s1', 't1', 0, 'click', '#a', 'css')""",
    """INSERT INTO steps (id, test_case_id, order_index, action, selector,
       selector_strategy) VALUES ('s2', 't2', 0, 'click', '#b', 'css')""",
    "INSERT INTO test_runs (id, test_case_id, status) VALUES ('r1','t1','passed')",
    """INSERT INTO step_results (id, test_run_id, step_id, status, duration_ms)
       VALUES ('sr1', 'r1', 's1', 'passed', 12)""",
    """INSERT INTO evidences (id, test_run_id, type, file_path)
       VALUES ('e1', 'r1', 'video', 'a/b.webm')""",
]


@pytest_asyncio.fixture
async def legacy_engine(tmp_path):
    """A database in the shape it had before the models moved on.

    Wired like the application's engine, foreign keys and all, so the upgrade is
    exercised the way it actually runs.
    """
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'old.db'}")

    @event.listens_for(engine.sync_engine, "connect")
    def _enable_sqlite_fks(dbapi_conn, _record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    async with engine.begin() as conn:
        for statement in [*LEGACY_SCHEMA, *SEED]:
            await conn.execute(text(statement))
    yield engine
    await engine.dispose()


async def _scalar(engine, sql: str):
    async with engine.connect() as conn:
        return (await conn.execute(text(sql))).scalar()


@pytest.mark.asyncio
async def test_columns_added_since_the_database_was_made(legacy_engine):
    await upgrade_schema(legacy_engine)

    # Reading them is the point: before the upgrade this raises "no such column".
    assert await _scalar(legacy_engine, "SELECT COUNT(frame_url) FROM steps") == 0
    assert (
        await _scalar(
            legacy_engine, "SELECT COUNT(*) FROM steps WHERE NOT is_exit_criteria"
        )
        == 2
    )


@pytest.mark.asyncio
async def test_delete_rules_are_repaired(legacy_engine):
    await upgrade_schema(legacy_engine)

    async with legacy_engine.connect() as conn:
        rules = {
            row[3]: (row[6] or "NO ACTION")
            for row in await conn.execute(
                text("PRAGMA foreign_key_list(step_results)")
            )
        }
    assert rules == {"test_run_id": "CASCADE", "step_id": "CASCADE"}


@pytest.mark.asyncio
async def test_deleting_a_test_case_takes_its_runs_with_it(legacy_engine):
    """The failure this repairs: a run's results pinned the test case in place.

    Nothing here turns enforcement on by hand - the upgrade has to leave the
    engine's own connections enforcing it, or every later cascade is skipped.
    """
    await upgrade_schema(legacy_engine)

    async with legacy_engine.begin() as conn:
        await conn.execute(text("DELETE FROM test_cases WHERE id = 't1'"))

    assert await _scalar(legacy_engine, "SELECT COUNT(*) FROM test_runs") == 0
    assert await _scalar(legacy_engine, "SELECT COUNT(*) FROM step_results") == 0
    assert await _scalar(legacy_engine, "SELECT COUNT(*) FROM evidences") == 0
    # The other test case and its step are untouched.
    assert await _scalar(legacy_engine, "SELECT COUNT(*) FROM test_cases") == 1
    assert await _scalar(legacy_engine, "SELECT COUNT(*) FROM steps") == 1


@pytest.mark.asyncio
async def test_foreign_keys_survive_the_upgrade(legacy_engine):
    """The rebuild switches enforcement off; it must not leave it that way."""
    await upgrade_schema(legacy_engine)

    for _ in range(3):  # whichever pooled connection comes back
        async with legacy_engine.connect() as conn:
            assert (await conn.execute(text("PRAGMA foreign_keys"))).scalar() == 1


@pytest.mark.asyncio
async def test_upgrading_twice_changes_nothing(legacy_engine):
    await upgrade_schema(legacy_engine)
    await upgrade_schema(legacy_engine)

    assert await _scalar(legacy_engine, "SELECT COUNT(*) FROM steps") == 2
    assert await _scalar(legacy_engine, "SELECT COUNT(*) FROM step_results") == 1
    async with legacy_engine.connect() as conn:
        leftovers = [
            row[0]
            for row in await conn.execute(
                text("SELECT name FROM sqlite_master WHERE name LIKE '%__rebuild'")
            )
        ]
    assert leftovers == []
