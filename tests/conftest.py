"""Database fixtures shared by every suite that needs storage.

Locally these run on in-memory SQLite, which needs no setup and finishes instantly. Point
``TEST_DATABASE_URL`` at a Postgres instance — CI does — and the same tests run there, which
is what catches the places where the two dialects disagree.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from padel_tour import settings as padel_settings
from padel_tour.db import create_all, create_engine, create_session_factory, drop_all
from padel_tour.db.config import normalise_url
from padel_tour.settings import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite must not read the developer's ``.env``.

    That file holds a real bot token and a real database URL. A test run that picks them up
    is a test run that can reach production by accident — and it would do it quietly, on a
    machine where everything looks fine.
    """
    monkeypatch.setattr(padel_settings, "ENV_FILE", None)


def configured_database_url() -> str:
    configured = settings().test_database_url.strip()
    return normalise_url(configured) if configured else "sqlite+aiosqlite:///:memory:"


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    """A fresh schema per test, torn down afterwards."""
    engine = create_engine(configured_database_url())
    await drop_all(engine)
    await create_all(engine)
    try:
        yield engine
    finally:
        await drop_all(engine)
        await engine.dispose()


@pytest.fixture
def factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory — for tests that need a second, independent session."""
    return create_session_factory(engine)


@pytest.fixture
async def session(
    factory: async_sessionmaker[AsyncSession],
) -> AsyncIterator[AsyncSession]:
    """A working session.

    Teardown rolls back rather than commits: a test that deliberately violates a constraint
    leaves the transaction poisoned, and committing on the way out would turn its clean
    assertion into a fixture error. Tests that need data to outlive the session commit
    themselves — which is also what real callers do.
    """
    async with factory() as session:
        try:
            yield session
        finally:
            await session.rollback()
