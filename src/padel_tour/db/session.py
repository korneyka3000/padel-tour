"""Engine and session plumbing.

Callers get sessions from :func:`session_scope`, which commits on success and rolls back on
any exception. Service functions never commit for themselves — the caller owns the
transaction, so several of them can be composed into one unit of work.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import database_url, is_sqlite
from .models import Base

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


def create_engine(url: str | None = None, *, echo: bool = False) -> AsyncEngine:
    """Build an async engine for ``url``, defaulting to the configured database."""
    resolved = url or database_url()
    engine = create_async_engine(resolved, echo=echo)

    if is_sqlite(resolved):
        _enforce_sqlite_foreign_keys(engine)

    return engine


def _enforce_sqlite_foreign_keys(engine: AsyncEngine) -> None:
    """Turn on foreign keys for SQLite, which ignores them by default.

    Without this, local runs silently accept rows that Postgres rejects in CI — exactly the
    divergence that having two dialects is supposed to catch.
    """

    @event.listens_for(engine.sync_engine, "connect")
    def _set_pragma(dbapi_connection: object, _record: object) -> None:
        cursor = dbapi_connection.cursor()  # ty: ignore[unresolved-attribute]
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory that leaves objects usable after commit."""
    return async_sessionmaker(engine, expire_on_commit=False)


@asynccontextmanager
async def session_scope(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """One unit of work: commit on success, roll back on failure."""
    async with factory() as session:
        try:
            yield session
        except BaseException:
            await session.rollback()
            raise
        else:
            await session.commit()


async def create_all(engine: AsyncEngine) -> None:
    """Create the schema directly, skipping Alembic.

    For tests and for the local SQLite file. Anything deployed goes through migrations.
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def drop_all(engine: AsyncEngine) -> None:
    """Drop every table. Tests only."""
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
