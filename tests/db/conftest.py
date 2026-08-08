"""Fixtures specific to storage tests. Connection plumbing lives in ``tests/conftest.py``."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from padel_tour.engine import Format, PairingPattern, TournamentConfig
from padel_tour.services import add_player, create_group

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

EIGHT_NAMES = ("Ann", "Ben", "Cara", "Dan", "Eve", "Finn", "Gina", "Hugo")


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
