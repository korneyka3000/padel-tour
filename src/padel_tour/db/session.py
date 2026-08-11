"""Engine and session plumbing.

Callers get sessions from :func:`session_scope`, which commits on success and rolls back on
any exception. Service functions never commit for themselves — the caller owns the
transaction, so several of them can be composed into one unit of work.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from .config import database_url
from .models import Base

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


#: Drop a pooled connection after this long rather than trusting it.
#:
#: Comfortably under Neon's own idle timeout, so a connection is retired by us before it is
#: closed under us.
POOL_RECYCLE_SECONDS = 240


def create_engine(url: str | None = None, *, echo: bool = False) -> AsyncEngine:
    """Build an async engine for ``url``, defaulting to the configured database.

    **Connections are checked before they are used.** In production this runs as a
    serverless function: the instance is frozen between requests, sometimes for hours, and
    Neon closes the connection at its end while our pool still believes in it. The next
    request then dies on ``connection is closed`` — which is what happened to ``/login``,
    and which looks to the person typing it like the bot ignoring them.

    ``pool_pre_ping`` costs one cheap round trip on checkout and turns that into a silent
    reconnect. ``pool_recycle`` retires connections before the far end does, so the ping
    usually has nothing to fix.
    """
    return create_async_engine(
        _tuned_for_poolers(url or database_url()),
        echo=echo,
        pool_pre_ping=True,
        pool_recycle=POOL_RECYCLE_SECONDS,
    )


#: What turns the asyncpg statement cache off. A URL parameter, not an engine keyword —
#: passing it to ``create_async_engine`` raises ``TypeError`` at construction, which is a
#: deploy that fails rather than an application that misbehaves, but a deploy that fails all
#: the same.
_NO_STATEMENT_CACHE = "prepared_statement_cache_size=0"


def _tuned_for_poolers(url: str) -> str:
    """Turn off the statement cache when the far end is a connection pooler.

    Neon's pooled endpoint is pgbouncer in transaction mode, where a prepared statement
    outlives the transaction that made it but not the backend it was made on — so a cached
    one eventually points at nothing and comes back as ``DuplicatePreparedStatementError``,
    intermittently and under load. SQLAlchemy's own advice for pgbouncer is to keep no
    cache.

    Only for the pooled host. Against a direct connection — every test, and local
    development — prepared statements are free performance and stay switched on.
    """
    if "-pooler." not in url or _NO_STATEMENT_CACHE.split("=", maxsplit=1)[0] in url:
        return url
    separator = "&" if "?" in url else "?"
    return f"{url}{separator}{_NO_STATEMENT_CACHE}"


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
