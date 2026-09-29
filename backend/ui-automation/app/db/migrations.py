"""Schema upkeep for databases created by an earlier version.

`Base.metadata.create_all` adds new tables but never touches a table that
already exists, so a database from before a column was introduced keeps working
until the first query mentions it. This walks the mapped tables and adds
whatever is missing, which is all SQLite can do without a rebuild.

Nothing here drops or rewrites data.
"""

import logging

from sqlalchemy import MetaData, inspect
from sqlalchemy.schema import CreateTable

from app.models.base import Base

logger = logging.getLogger(__name__)


def _literal(value) -> str | None:
    """Render a column default SQLite will accept in an ALTER TABLE clause."""
    if isinstance(value, bool):
        return "1" if value else "0"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        escaped = value.replace("'", "''")
        return f"'{escaped}'"
    return None


def _add_missing_columns(connection) -> None:
    inspector = inspect(connection)
    existing_tables = set(inspector.get_table_names())

    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue  # create_all just made it, so it is already current.
        present = {c["name"] for c in inspector.get_columns(table.name)}

        for column in table.columns:
            if column.name in present:
                continue
            clause = (
                f'ALTER TABLE "{table.name}" ADD COLUMN "{column.name}" '
                f"{column.type.compile(connection.dialect)}"
            )
            # Rows that already exist need something to hold, so carry the
            # model's default across.
            default = _literal(getattr(column.default, "arg", None))
            if default is not None:
                clause += f" DEFAULT {default}"

            connection.exec_driver_sql(clause)
            logger.info("Added missing column %s.%s", table.name, column.name)


def _wanted_ondelete(table) -> dict[str, str]:
    """The ON DELETE action the model declares, per constrained column."""
    wanted: dict[str, str] = {}
    for constraint in table.foreign_key_constraints:
        action = (constraint.ondelete or "NO ACTION").upper()
        for element in constraint.elements:
            wanted[element.parent.name] = action
    return wanted


def _current_ondelete(connection, table_name: str) -> dict[str, str]:
    rows = connection.exec_driver_sql(
        f'PRAGMA foreign_key_list("{table_name}")'
    ).mappings()
    return {r["from"]: (r["on_delete"] or "NO ACTION").upper() for r in rows}


def _stale_cascades(connection, existing_tables: set[str]) -> list:
    """Tables whose foreign keys no longer say what the model says.

    SQLite writes foreign keys into the table definition, so a database made
    before `ondelete` was declared still has the old rules - and deleting a
    test case that has runs fails on them.
    """
    stale = []
    for table in Base.metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        wanted = _wanted_ondelete(table)
        if not wanted:
            continue
        current = _current_ondelete(connection, table.name)
        if any(current.get(column) != action for column, action in wanted.items()):
            stale.append(table)
    return stale


def _rebuild(connection, table) -> None:
    """Recreate one table with the current definition, rows carried across.

    SQLite cannot alter a foreign key in place; the documented way round it is
    to build the replacement beside the original and swap them over.
    """
    inspector = inspect(connection)
    old_columns = {c["name"] for c in inspector.get_columns(table.name)}
    shared = [c.name for c in table.columns if c.name in old_columns]
    if not shared:
        return

    staging = f"{table.name}__rebuild"
    replacement = _staging_table(table, staging)
    connection.exec_driver_sql(
        str(CreateTable(replacement).compile(dialect=connection.dialect))
    )
    names = ", ".join(f'"{c}"' for c in shared)
    connection.exec_driver_sql(
        f'INSERT INTO "{staging}" ({names}) SELECT {names} FROM "{table.name}"'
    )
    connection.exec_driver_sql(f'DROP TABLE "{table.name}"')
    connection.exec_driver_sql(
        f'ALTER TABLE "{staging}" RENAME TO "{table.name}"'
    )
    logger.info("Rebuilt %s to restore its delete rules", table.name)


def _staging_table(table, staging: str):
    """A copy of `table` under another name, in a metadata of its own.

    Every table comes across, otherwise the copy's foreign keys have nothing to
    point at when the DDL is compiled.
    """
    scratch = MetaData()
    for other in Base.metadata.sorted_tables:
        other.to_metadata(scratch)
    return scratch.tables[table.name].to_metadata(scratch, name=staging)


def _repair_cascades(connection) -> None:
    """Bring foreign keys in line with the models, if any have drifted.

    Enforcement has to be off for the swap - dropping a parent table whose rows
    are still referenced is the whole point - and SQLite only honours that
    outside a transaction, so the rebuild brackets its own.
    """
    inspector = inspect(connection)
    stale = _stale_cascades(connection, set(inspector.get_table_names()))
    if not stale:
        return

    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    if connection.exec_driver_sql("PRAGMA foreign_keys").scalar():
        raise RuntimeError(
            "Foreign keys cannot be repaired while a transaction is open."
        )

    connection.exec_driver_sql("BEGIN")
    try:
        for table in stale:
            _rebuild(connection, table)
        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if broken:
            # Better a working old schema than a half-migrated new one.
            raise RuntimeError(f"foreign keys broken after rebuild: {broken[:5]}")
        connection.exec_driver_sql("COMMIT")
    except Exception:
        connection.exec_driver_sql("ROLLBACK")
        raise
    finally:
        # Back on outside the transaction, or the pool would hand out a
        # connection that silently skips every cascade.
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")


async def upgrade_schema(engine) -> None:
    """Create new tables, then bring an older database up to the models."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        if engine.dialect.name == "sqlite":
            await conn.run_sync(_add_missing_columns)

    if engine.dialect.name != "sqlite":
        return

    # Its own connection, in autocommit: switching foreign key enforcement is
    # ignored inside a transaction, and this one is thrown away afterwards so a
    # half-applied pragma can never outlive the upgrade.
    async with engine.connect() as conn:
        autocommit = await conn.execution_options(isolation_level="AUTOCOMMIT")
        try:
            await autocommit.run_sync(_repair_cascades)
        finally:
            await autocommit.invalidate()
