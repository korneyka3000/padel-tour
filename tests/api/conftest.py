"""API fixtures.

The app is driven through an ASGI transport rather than a real server: no port, no waiting,
and the same code path a request would take.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from httpx import ASGITransport, AsyncClient

from padel_tour.api import create_app
from padel_tour.engine import Format, PairingPattern, TournamentConfig
from padel_tour.services import add_player, create_group, record_score, start_tournament

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from padel_tour.services import TournamentView

NAMES = ("Аня", "Боря", "Вика", "Гриша", "Даша", "Егор", "Жанна", "Зина")


@pytest.fixture
def app(factory: async_sessionmaker[AsyncSession]) -> FastAPI:
    """The real app, pointed at the test database."""
    application = create_app()
    application.state.session_factory = factory
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


async def seed_tournament(
    session: AsyncSession,
    *,
    fmt: Format = Format.AMERICANO,
    rounds_to_play: int = 0,
) -> TournamentView:
    """A group of eight with a tournament, optionally part-played."""
    group = await create_group(session, "Вторничный падел")
    players = [(await add_player(session, group.id, name)).id for name in NAMES]

    config = (
        TournamentConfig(fmt, points_per_match=24)
        if fmt is Format.AMERICANO
        else TournamentConfig(
            fmt, points_per_match=24, pairing_pattern=PairingPattern.CROSSOVER, rounds=4
        )
    )
    view = await start_tournament(session, group.id, players, config, seed=11)

    for number in range(1, rounds_to_play + 1):
        for match in view.rounds[number - 1].matches:
            view = await record_score(
                session,
                view.id,
                round_no=number,
                court=match.court,
                score_a=14,
                score_b=10,
            )
    await session.commit()
    return view
