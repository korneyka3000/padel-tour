"""Shared plumbing: the database engine, sessions, and turning our errors into statuses."""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from padel_tour.db import create_engine, create_session_factory, database_url

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _engine_and_factory() -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    """One engine per process, not per request.

    Serverless reuses warm instances, so a pool that lives for a single request is just a
    slow way of having no pool at all.
    """
    engine = create_engine(database_url())
    return engine, create_session_factory(engine)


def session_factory() -> async_sessionmaker[AsyncSession]:
    return _engine_and_factory()[1]


async def dispose_engine() -> None:
    """Close the pool on shutdown. Also lets tests start from a clean engine."""
    engine, _ = _engine_and_factory()
    await engine.dispose()
    _engine_and_factory.cache_clear()


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    """A session per request.

    Read-only endpoints do not commit; the rollback on the way out simply ends the
    transaction. A test can override the factory by putting one on ``app.state``.
    """
    factory: async_sessionmaker[AsyncSession] = (
        getattr(request.app.state, "session_factory", None) or session_factory()
    )
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()


Session = Annotated[AsyncSession, Depends(get_session)]
