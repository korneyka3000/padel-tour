"""The bot as an adapter.

Telegram is one way in, not the way in. What these pin down is that a Telegram id resolves
to an account of ours, and that the invitation a chat accepts is the same object the web
accepts — the link is to a *player*, not to a surface.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, cast

import pytest

from padel_tour.bot import handlers
from padel_tour.db import PROVIDER_EMAIL, PROVIDER_TELEGRAM, Player
from padel_tour.services import (
    account_for_identity,
    add_player,
    create_group,
    create_invite,
    ensure_identity,
    redeem_magic_link,
)
from padel_tour.services.errors import InvalidTokenError

if TYPE_CHECKING:
    from aiogram import Bot
    from aiogram.types import Message
    from sqlalchemy.ext.asyncio import AsyncSession

CHAT_ID = -100500
ANYA_TELEGRAM = 4242


@dataclass
class FakeChat:
    id: int
    title: str = ""
    type: str = "group"


@dataclass
class FakeUser:
    id: int
    full_name: str = "Аня"


@dataclass
class FakeStartMessage:
    """Just enough of a Message for ``/start`` — including the reply it gets back."""

    text: str
    chat: FakeChat
    from_user: FakeUser | None
    replies: list[str] = field(default_factory=list)

    async def reply(self, text: str, **_: object) -> None:
        self.replies.append(text)


def start(payload: str = "", *, user_id: int = ANYA_TELEGRAM) -> FakeStartMessage:
    return FakeStartMessage(
        text=f"/start {payload}".strip(),
        chat=FakeChat(CHAT_ID, "Вторничный падел"),
        from_user=FakeUser(user_id),
    )


async def send(session: AsyncSession, message: FakeStartMessage) -> FakeStartMessage:
    """Deliver ``/start`` the way aiogram would, minus its type check.

    ``bot`` is never reached: a ``/start`` carrying a token replies and stops, and these are
    all about the token.
    """
    await handlers.on_start(cast("Message", message), session, cast("Bot", None))
    return message


# ------------------------------------------------------------------------------ accounts


async def test_an_unfamiliar_telegram_id_mints_an_account(session: AsyncSession) -> None:
    """No sign-up step: the bot already knows it is talking to a stable person."""
    account = await handlers._account_for(session, ANYA_TELEGRAM)

    assert account.id is not None
    found = await account_for_identity(session, PROVIDER_TELEGRAM, str(ANYA_TELEGRAM))
    assert found is not None
    assert found.id == account.id


async def test_a_familiar_telegram_id_is_the_same_person(session: AsyncSession) -> None:
    first = await handlers._account_for(session, ANYA_TELEGRAM)
    second = await handlers._account_for(session, ANYA_TELEGRAM)
    assert first.id == second.id


# --------------------------------------------------------------------------- invitations


async def test_a_deep_link_claims_the_player_it_names(session: AsyncSession) -> None:
    owner = await ensure_identity(session, PROVIDER_EMAIL, "owner@example.test")
    group = await create_group(session, "Вторничный падел", owner_account_id=owner.id)
    anya = await add_player(session, group.id, "Аня", actor=owner)
    token = await create_invite(session, owner, anya.id)

    message = await send(session, start(token))

    assert "Аня" in message.replies[-1]
    account = await handlers._account_for(session, ANYA_TELEGRAM)
    claimed = await session.get(Player, anya.id)
    assert claimed is not None
    assert claimed.account_id == account.id


async def test_a_deep_link_that_means_nothing_says_so(session: AsyncSession) -> None:
    """A stale link in a chat gets an explanation, not a stack trace."""
    message = await send(session, start("not-a-real-token"))
    assert "Приглашение не найдено" in message.replies[-1]


async def test_a_used_deep_link_is_refused(session: AsyncSession) -> None:
    owner = await ensure_identity(session, PROVIDER_EMAIL, "owner@example.test")
    group = await create_group(session, "Вторничный падел", owner_account_id=owner.id)
    anya = await add_player(session, group.id, "Аня", actor=owner)
    token = await create_invite(session, owner, anya.id)
    await send(session, start(token))

    second = await send(session, start(token, user_id=777))
    assert "уже использовано" in second.replies[-1]


# ------------------------------------------------------------------------ into the web


def login(*, chat_type: str, user_id: int = ANYA_TELEGRAM) -> FakeStartMessage:
    return FakeStartMessage(
        text="/login",
        chat=FakeChat(CHAT_ID, "Вторничный падел", chat_type),
        from_user=FakeUser(user_id),
    )


async def test_a_sign_in_link_is_never_posted_in_a_group(session: AsyncSession) -> None:
    """The link signs its holder in as whoever asked for it.

    Posted in a group chat it would hand eight people one member's account, and Telegram
    has no way to show a message to only one of them. So the group gets directions, not a
    link — and the test is here because this is the kind of thing that gets "simplified"
    later by somebody who reads the handler and not the reason.
    """
    message = login(chat_type="group")

    await handlers.on_login(cast("Message", message), session)

    assert "/auth/enter?token=" not in message.replies[-1]
    assert "личку" in message.replies[-1]


async def test_a_private_chat_gets_a_working_link(session: AsyncSession) -> None:
    """No mail server anywhere in this: the bot has already established who this is, which
    is the entire job an emailed link exists to do."""
    message = login(chat_type="private")

    await handlers.on_login(cast("Message", message), session)

    reply = message.replies[-1]
    assert "/auth/enter?token=" in reply

    token = reply.partition("?token=")[2].strip()
    account = await redeem_magic_link(session, token)
    assert account is not None


async def test_the_link_signs_in_as_the_telegram_account_not_a_new_one(
    session: AsyncSession,
) -> None:
    """Resolving by address would mint a second account and lose the claimed player."""
    message = login(chat_type="private")
    await handlers.on_login(cast("Message", message), session)
    token = message.replies[-1].partition("?token=")[2].strip()

    signed_in = await redeem_magic_link(session, token)

    expected = await account_for_identity(session, PROVIDER_TELEGRAM, str(ANYA_TELEGRAM))
    assert expected is not None
    assert signed_in.id == expected.id


async def test_a_link_works_once(session: AsyncSession) -> None:
    message = login(chat_type="private")
    await handlers.on_login(cast("Message", message), session)
    token = message.replies[-1].partition("?token=")[2].strip()
    await redeem_magic_link(session, token)

    with pytest.raises(InvalidTokenError):
        await redeem_magic_link(session, token)
