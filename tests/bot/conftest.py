"""Fixtures for bot tests.

Screens are pure, so most tests here need a tournament view and nothing else — no Telegram,
no network. The database fixtures come from ``tests/conftest.py``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from padel_tour.engine import Format, PairingPattern, TournamentConfig
from padel_tour.services import add_player, create_group, record_score, start_tournament

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account
    from padel_tour.services import TournamentView

NAMES = ("Аня", "Боря", "Вика", "Гриша", "Даша", "Егор", "Жанна", "Зина")


async def make_tournament(
    session: AsyncSession,
    *,
    fmt: Format = Format.AMERICANO,
    rounds: int | None = None,
    points: int = 24,
    pattern: PairingPattern = PairingPattern.CROSSOVER,
    organiser: Account | None = None,
) -> TournamentView:
    """A real tournament with Russian names, as a live chat would have."""
    group = await create_group(session, "Вторничный падел")
    players = [(await add_player(session, group.id, name)).id for name in NAMES]

    config = (
        TournamentConfig(fmt, points_per_match=points)
        if fmt is Format.AMERICANO
        else TournamentConfig(
            fmt, points_per_match=points, pairing_pattern=pattern, rounds=rounds or 4
        )
    )
    return await start_tournament(session, group.id, players, config, seed=7, actor=organiser)


async def play_round(session: AsyncSession, view: TournamentView, number: int) -> TournamentView:
    for match in view.rounds[number - 1].matches:
        view = await record_score(
            session,
            view.id,
            round_no=number,
            court=match.court,
            score_a=14,
            score_b=10,
        )
    return view


@pytest.fixture
async def americano(session: AsyncSession) -> TournamentView:
    return await make_tournament(session)


@pytest.fixture
async def mexicano(session: AsyncSession) -> TournamentView:
    return await make_tournament(session, fmt=Format.MEXICANO, rounds=3)
