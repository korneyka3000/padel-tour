"""Questions about the database itself, rather than about anything in it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text

if TYPE_CHECKING:
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
