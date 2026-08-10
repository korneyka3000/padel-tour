"""Database fixtures shared by every suite that needs storage.

**Postgres, always.** This used to be SQLite locally and Postgres only in CI, which meant
the suite a person actually ran was not the suite that decided whether the code worked. Two
bugs reached main that way — a migration nothing local could execute, and a pair of
Postgres-only failures the SQLite run could not see — and both were found by the machine
rather than by the person who wrote them.

The instance comes from testcontainers: started once for the session, thrown away after. No
compose file to keep in step with CI, no "did you remember to start the database", and the
same image in both places. It needs Docker, which is the price of the two dialects being
one dialect.

``TEST_DATABASE_URL`` still wins if it is set, for a machine that already has Postgres and
would rather not pay the startup.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from testcontainers.community.postgres import PostgresContainer

from padel_tour import settings as padel_settings
from padel_tour.db import create_all, create_engine, create_session_factory, drop_all
from padel_tour.db.config import normalise_url
from padel_tour.settings import settings

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Iterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

#: Pinned rather than ``latest``: the database the suite runs against is part of the test,
#: and a silent major-version bump is the kind of thing that breaks a Monday.
POSTGRES_IMAGE = "postgres:17-alpine"


@pytest.fixture(autouse=True)
def _no_dotenv(monkeypatch: pytest.MonkeyPatch) -> None:
    """The suite must not read the developer's ``.env``.

    That file holds a real bot token and a real database URL. A test run that picks them up
    is a test run that can reach production by accident — and it would do it quietly, on a
    machine where everything looks fine.
    """
    monkeypatch.setattr(padel_settings, "ENV_FILE", None)


@pytest.fixture(scope="session")
def database_url() -> Iterator[str]:
    """Where the suite's Postgres lives.

    Session-scoped because starting a container costs a second or two and creating the
    schema costs nothing — so one instance serves the whole run, and isolation stays where
    it already was, in the per-test drop and create below.
    """
    configured = settings().test_database_url.strip()
    if configured:
        yield normalise_url(configured)
        return

    with PostgresContainer(POSTGRES_IMAGE, driver="asyncpg") as container:
        yield container.get_connection_url()


@pytest.fixture
async def engine(database_url: str) -> AsyncIterator[AsyncEngine]:
    """A fresh schema per test, torn down afterwards."""
    engine = create_engine(database_url)
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
