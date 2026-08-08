"""Signing in.

There is no password anywhere in this system, so a link in an inbox is the whole of the
proof. These tests pin what that link is allowed to do, and for how long.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select, update

from padel_tour.db import PROVIDER_EMAIL, PROVIDER_TELEGRAM, LoginSession, MagicLink, utc_now
from padel_tour.services.accounts import (
    account_for_identity,
    account_for_session,
    close_all_sessions,
    close_session,
    ensure_identity,
    open_session,
    redeem_magic_link,
    request_magic_link,
)
from padel_tour.services.errors import (
    InvalidTokenError,
    TokenExpiredError,
    TooManyRequestsError,
)
from padel_tour.services.mail import InMemoryMailer

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

LINK_BASE = "https://example.test/auth/enter"
EMAIL = "anya@example.test"


def token_from(mailer: InMemoryMailer, address: str = EMAIL) -> str:
    message = mailer.last_to(address)
    assert message is not None, f"no mail sent to {address}"
    _, _, token = message.body.partition("?token=")
    return token.split()[0]


async def ask_for_link(session: AsyncSession, address: str = EMAIL) -> tuple[InMemoryMailer, str]:
    mailer = InMemoryMailer()
    await request_magic_link(session, address, mailer=mailer, link_base=LINK_BASE)
    return mailer, token_from(mailer, address)


# ------------------------------------------------------------------------ asking for one


async def test_a_link_arrives(session: AsyncSession) -> None:
    mailer, token = await ask_for_link(session)
    assert mailer.sent[0].to == EMAIL
    assert LINK_BASE in mailer.sent[0].body
    assert token


async def test_the_address_is_normalised(session: AsyncSession) -> None:
    """Otherwise Anya@… and anya@… are two people."""
    mailer = InMemoryMailer()
    await request_magic_link(session, "  ANYA@Example.Test ", mailer=mailer, link_base=LINK_BASE)
    assert mailer.sent[0].to == EMAIL


async def test_a_second_request_within_the_minute_is_refused(session: AsyncSession) -> None:
    """The address is unverified, so unlimited sending fills a stranger's inbox."""
    await ask_for_link(session)
    with pytest.raises(TooManyRequestsError):
        await ask_for_link(session)


async def test_a_second_request_later_is_fine(session: AsyncSession) -> None:
    mailer, _ = await ask_for_link(session)

    await session.execute(update(MagicLink).values(created_at=utc_now() - timedelta(minutes=5)))

    await request_magic_link(session, EMAIL, mailer=mailer, link_base=LINK_BASE)
    assert len(mailer.sent) == 2


# ----------------------------------------------------------------------------- using one


async def test_a_link_signs_you_in(session: AsyncSession) -> None:
    _, token = await ask_for_link(session)
    account = await redeem_magic_link(session, token)
    assert account.id is not None
    assert await account_for_identity(session, PROVIDER_EMAIL, EMAIL) is not None


async def test_signing_in_twice_is_the_same_person(session: AsyncSession) -> None:
    _, first_token = await ask_for_link(session)
    first = await redeem_magic_link(session, first_token)

    await session.execute(update(MagicLink).values(created_at=utc_now() - timedelta(minutes=5)))
    mailer = InMemoryMailer()
    await request_magic_link(session, EMAIL, mailer=mailer, link_base=LINK_BASE)
    second = await redeem_magic_link(session, token_from(mailer))

    assert first.id == second.id


async def test_a_link_works_once(session: AsyncSession) -> None:
    """A forwarded email must not be a spare key."""
    _, token = await ask_for_link(session)
    await redeem_magic_link(session, token)

    with pytest.raises(InvalidTokenError):
        await redeem_magic_link(session, token)


async def test_an_expired_link_is_refused(session: AsyncSession) -> None:
    _, token = await ask_for_link(session)
    await session.execute(update(MagicLink).values(expires_at=utc_now() - timedelta(seconds=1)))

    with pytest.raises(TokenExpiredError):
        await redeem_magic_link(session, token)


async def test_a_made_up_link_is_refused(session: AsyncSession) -> None:
    with pytest.raises(InvalidTokenError):
        await redeem_magic_link(session, "not-a-real-token")


async def test_the_raw_token_is_never_stored(session: AsyncSession) -> None:
    """A leaked database must not be a set of keys."""
    _, token = await ask_for_link(session)
    row = (await session.execute(select(MagicLink))).scalars().one()
    assert row.token_hash != token
    assert token not in row.token_hash


# ------------------------------------------------------------------------------ sessions


async def test_a_session_identifies_its_account(session: AsyncSession) -> None:
    account = await ensure_identity(session, PROVIDER_EMAIL, EMAIL)
    token = await open_session(session, account)

    found = await account_for_session(session, token)
    assert found is not None
    assert found.id == account.id


async def test_an_unknown_session_is_nobody(session: AsyncSession) -> None:
    assert await account_for_session(session, "nonsense") is None


async def test_an_expired_session_is_nobody(session: AsyncSession) -> None:
    account = await ensure_identity(session, PROVIDER_EMAIL, EMAIL)
    token = await open_session(session, account)
    await session.execute(update(LoginSession).values(expires_at=utc_now() - timedelta(seconds=1)))

    assert await account_for_session(session, token) is None


async def test_signing_out_ends_the_session(session: AsyncSession) -> None:
    account = await ensure_identity(session, PROVIDER_EMAIL, EMAIL)
    token = await open_session(session, account)

    await close_session(session, token)
    assert await account_for_session(session, token) is None


async def test_signing_out_of_an_unknown_session_is_not_an_error(
    session: AsyncSession,
) -> None:
    """The caller asked to be signed out, and they are."""
    await close_session(session, "nonsense")


async def test_signing_out_everywhere(session: AsyncSession) -> None:
    """The reason sessions are rows rather than signed tokens."""
    account = await ensure_identity(session, PROVIDER_EMAIL, EMAIL)
    phone = await open_session(session, account)
    laptop = await open_session(session, account)

    await close_all_sessions(session, account)

    assert await account_for_session(session, phone) is None
    assert await account_for_session(session, laptop) is None


# ---------------------------------------------------------------------------- identities


async def test_an_unfamiliar_identity_mints_an_account(session: AsyncSession) -> None:
    """What lets a bot recognise someone with no sign-up step at all."""
    account = await ensure_identity(session, PROVIDER_TELEGRAM, "42")
    assert account.id is not None


async def test_a_familiar_identity_returns_the_same_account(session: AsyncSession) -> None:
    first = await ensure_identity(session, PROVIDER_TELEGRAM, "42")
    second = await ensure_identity(session, PROVIDER_TELEGRAM, "42")
    assert first.id == second.id


async def test_identities_of_different_providers_are_different_people_until_linked(
    session: AsyncSession,
) -> None:
    """Nothing connects an email to a Telegram id on its own — an invite does that."""
    by_mail = await ensure_identity(session, PROVIDER_EMAIL, EMAIL)
    by_telegram = await ensure_identity(session, PROVIDER_TELEGRAM, "42")
    assert by_mail.id != by_telegram.id
