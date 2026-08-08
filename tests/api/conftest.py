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
from padel_tour.services.mail import InMemoryMailer

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from padel_tour.db import Account
    from padel_tour.services import TournamentView

NAMES = ("Аня", "Боря", "Вика", "Гриша", "Даша", "Егор", "Жанна", "Зина")


@pytest.fixture
def mailer() -> InMemoryMailer:
    """Sign-in mail, remembered rather than sent."""
    return InMemoryMailer()


@pytest.fixture
def app(factory: async_sessionmaker[AsyncSession], mailer: InMemoryMailer) -> FastAPI:
    """The real app, pointed at the test database."""
    application = create_app()
    application.state.session_factory = factory
    application.state.mailer = mailer
    return application


@pytest.fixture
async def client(app: FastAPI) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client


#: ``example.com`` rather than the ``example.test`` used elsewhere: the API validates the
#: address, and email-validator refuses reserved special-use names like ``.test``.
OWNER_EMAIL = "owner@example.com"


async def sign_in(client: AsyncClient, mailer: InMemoryMailer, email: str = OWNER_EMAIL) -> str:
    """Walk the real sign-in: ask for a link, read the mail, follow it.

    Returns the address, so a test can look up the account it just created. The cookie ends
    up in the client's jar, which is what every subsequent request needs.
    """
    asked = await client.post("/api/auth/magic-link", json={"email": email})
    assert asked.status_code == 202, asked.text

    message = mailer.last_to(email)
    assert message is not None, f"no mail sent to {email}"
    token = message.body.partition("?token=")[2].split()[0]

    entered = await client.post("/api/auth/enter", json={"token": token})
    assert entered.status_code == 200, entered.text
    return email


async def seed_tournament(
    session: AsyncSession,
    *,
    fmt: Format = Format.AMERICANO,
    rounds_to_play: int = 0,
    owner: Account | None = None,
) -> TournamentView:
    """A group of eight with a tournament, optionally part-played.

    Without an owner the group is the shape a chat or the CLI makes: open to everyone. Pass
    one when the test is about who may see it.
    """
    group = await create_group(
        session, "Вторничный падел", owner_account_id=None if owner is None else owner.id
    )
    players = [(await add_player(session, group.id, name, actor=owner)).id for name in NAMES]

    config = (
        TournamentConfig(fmt, points_per_match=24)
        if fmt is Format.AMERICANO
        else TournamentConfig(
            fmt, points_per_match=24, pairing_pattern=PairingPattern.CROSSOVER, rounds=4
        )
    )
    view = await start_tournament(session, group.id, players, config, seed=11, actor=owner)

    for number in range(1, rounds_to_play + 1):
        for match in view.rounds[number - 1].matches:
            view = await record_score(
                session,
                view.id,
                round_no=number,
                court=match.court,
                score_a=14,
                score_b=10,
                actor=owner,
            )
    await session.commit()
    return view
