"""Questions about the database itself, rather than about anything in it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select, text

from padel_tour.db import Base

if TYPE_CHECKING:
    from collections.abc import Sequence

    from sqlalchemy import Column, Table
    from sqlalchemy.ext.asyncio import AsyncSession


async def ping(session: AsyncSession) -> None:
    """Can we reach it at all. Raises if not."""
    await session.execute(text("SELECT 1"))


async def present_columns(session: AsyncSession) -> set[tuple[str, str]]:
    """Every ``(table, column)`` the database actually has.

    For comparing against what the code believes in. A deploy that lands before its
    migration leaves the two disagreeing, and connectivity is perfect throughout — which is
    how production twice reported itself healthy while half the API answered 500 (Р-039,
    Р-043).
    """
    rows = await session.execute(
        text(
            "SELECT table_name, column_name FROM information_schema.columns "
            "WHERE table_schema = current_schema()"
        )
    )
    return {(row.table_name, row.column_name) for row in rows}


# ------------------------------------------------------ reading tables this code does not name
#
# Everywhere else in this package a query is written against a mapped class. These are
# written against ``Base.metadata``, because the caller is the admin table browser and its
# whole purpose is to show a table nobody anticipated — including a column added by a
# migration that no model here has heard of yet.
#
# That makes this the one place where a table is data rather than code, so the guard lives
# here rather than at the caller: a name arriving from a URL is looked up in the metadata and
# resolves to an object SQLAlchemy already knows how to quote, or it resolves to nothing.
# No name is ever interpolated into SQL.


def table_named(name: str) -> Table | None:
    """The mapped table with this name, or nothing."""
    return Base.metadata.tables.get(name)


async def count_rows(session: AsyncSession, table: Table) -> int:
    return int(await session.scalar(select(func.count()).select_from(table)) or 0)


async def table_sizes(session: AsyncSession) -> list[tuple[str, int]]:
    """Every mapped table with how many rows it holds, in dependency order."""
    return [(table.name, await count_rows(session, table)) for table in Base.metadata.sorted_tables]


async def read_page(
    session: AsyncSession,
    table: Table,
    columns: Sequence[Column[object]],
    *,
    limit: int,
    offset: int,
) -> list[tuple[object, ...]]:
    """One page of one table, in an order that is the same twice.

    Which order matters less than having one: paging through an unordered table repeats some
    rows and skips others, and gives the reader no sign of it. Newest first where a table
    records when, by primary key otherwise.
    """
    order = (
        [table.columns["created_at"].desc()]
        if "created_at" in table.columns
        else [column.asc() for column in table.primary_key.columns]
    )
    rows = await session.execute(select(*columns).order_by(*order).limit(limit).offset(offset))
    return [tuple(row) for row in rows]
