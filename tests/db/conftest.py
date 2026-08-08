"""Database fixtures.

Locally the suite runs on in-memory SQLite, which needs no setup and finishes instantly.
Point ``TEST_DATABASE_URL`` at a Postgres instance — CI does — and the same tests run there,
which is what catches the places where the two dialects disagree.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from padel_tour.db import (
    create_all,
    create_engine,
    create_session_factory,
    drop_all,
)
from padel_tour.db.config import normalise_url
from padel_tour.engine import Format, PairingPattern, TournamentConfig
from padel_tour.services import add_player, create_group

if TYPE_CHECKING:
    import uuid
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

EIGHT_NAMES = ("Ann", "Ben", "Cara", "Dan", "Eve", "Finn", "Gina", "Hugo")


def configured_database_url() -> str:
    configured = os.environ.get("TEST_DATABASE_URL", "").strip()
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


@pytest.fixture
async def group_id(session: AsyncSession) -> uuid.UUID:
    group = await create_group(session, "Tuesday Padel")
    return group.id


@pytest.fixture
async def eight_players(session: AsyncSession, group_id: uuid.UUID) -> list[uuid.UUID]:
    """Eight players, in a stable order."""
    return [(await add_player(session, group_id, name)).id for name in EIGHT_NAMES]


def americano_config(points: int = 24) -> TournamentConfig:
    return TournamentConfig(Format.AMERICANO, points_per_match=points)


def mexicano_config(
    points: int = 24,
    rounds: int = 4,
    pattern: PairingPattern = PairingPattern.CROSSOVER,
) -> TournamentConfig:
    return TournamentConfig(
        Format.MEXICANO,
        points_per_match=points,
        pairing_pattern=pattern,
        rounds=rounds,
    )
