"""Accounts: who a person is to us, and how they arrive.

An `Account` carries no provider-specific field. Signing in with an email, pressing a button
in Telegram, or anything added later are rows in `identities` — so a new integration never
reshapes the domain, and this module never learns the name of one.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from padel_tour import repositories
from padel_tour.db import PROVIDER_EMAIL, Account, LoginSession, MagicLink, utc_now

from .errors import InvalidTokenError, TokenExpiredError, TooManyRequestsError
from .tokens import hash_token, issue

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession

    from .mail import Mailer

#: Long enough to walk to your inbox, short enough that a forwarded email is not a key.
MAGIC_LINK_TTL = timedelta(minutes=15)

#: The absolute life of a session, counted from the sign-in and never extended. A padel
#: group plays weekly; signing in every week would be its own kind of friction.
SESSION_TTL = timedelta(days=30)

#: The other limit: a session nobody uses for this long is over, whatever its deadline says.
#:
#: The two together are the point. Without the absolute one a session could renew itself
#: forever; without this one a cookie copied off an unlocked laptop is good for a month even
#: though its owner never came back. Two weeks clears a holiday, which is the longest gap a
#: weekly game reasonably produces.
SESSION_IDLE_TTL = timedelta(days=14)

#: How stale ``last_used_at`` may get before a read bothers to write.
#:
#: Recording the exact moment of every request would put a write behind every authenticated
#: read, on a serverless function, over a transatlantic link. The column decides between
#: "days ago" and "weeks ago", so an hour of imprecision costs nothing and this costs at most
#: one write an hour per session.
TOUCH_AFTER = timedelta(hours=1)

#: One link per address per minute. The address is unverified by definition, so without
#: this the form is a way to fill a stranger's inbox.
MAGIC_LINK_COOLDOWN = timedelta(seconds=60)

SIGN_IN_SUBJECT = "Вход в Padel Tour"


async def get_account(session: AsyncSession, account_id: uuid.UUID) -> Account | None:
    return await repositories.account_by_id(session, account_id)


async def account_for_identity(
    session: AsyncSession, provider: str, external_id: str
) -> Account | None:
    """The account behind one external login, if we have seen it before."""
    return await repositories.account_by_identity(session, provider, external_id)


async def ensure_identity(
    session: AsyncSession, provider: str, external_id: str, *, display_name: str | None = None
) -> Account:
    """Find the account behind an external login, or mint one.

    This is what lets an integration recognise someone with no sign-up step at all: a bot
    already knows its own user id, so meeting an unfamiliar one is not an error, it is a
    first visit.
    """
    existing = await account_for_identity(session, provider, external_id)
    if existing is not None:
        # Fill a blank, never overwrite. Most accounts were minted before their integration
        # bothered to pass a name, and would otherwise stay nameless forever — the name is
        # only ever offered at the moment somebody arrives, and they have already arrived.
        if display_name and not existing.display_name:
            existing.display_name = display_name
            await session.flush()
        return existing

    account = await repositories.save(session, Account(display_name=display_name))
    await repositories.add_identity(session, account, provider, external_id)
    return account


async def attach_identity(
    session: AsyncSession, account: Account, provider: str, external_id: str
) -> None:
    """Add another way of signing in to an account that already exists."""
    await repositories.add_identity(session, account, provider, external_id)


# ----------------------------------------------------------------- signing in by email


def _sign_in_body(link: str) -> str:
    return (
        "Чтобы войти, откройте ссылку:\n\n"
        f"{link}\n\n"
        "Она сработает один раз и действует 15 минут.\n"
        "Если вход запрашивали не вы — просто не открывайте её."
    )


async def request_magic_link(
    session: AsyncSession, email: str, *, mailer: Mailer, link_base: str
) -> None:
    """Send a sign-in link.

    Says nothing about whether the address is known: the caller answers the same either
    way, or the form becomes a way to check who has an account here.
    """
    address = email.strip().lower()

    recent = await repositories.recent_magic_link(
        session, address, since=utc_now() - MAGIC_LINK_COOLDOWN
    )
    if recent is not None:
        raise TooManyRequestsError("a link is already on its way — check your inbox")

    raw, hashed = issue()
    await repositories.save(
        session, MagicLink(email=address, token_hash=hashed, expires_at=utc_now() + MAGIC_LINK_TTL)
    )

    await mailer.send(address, SIGN_IN_SUBJECT, _sign_in_body(f"{link_base}?token={raw}"))


async def issue_sign_in_link(session: AsyncSession, account: Account) -> str:
    """A single-use link for somebody we have already identified.

    The bot knows who is pressing its buttons, so it can hand that person a way into the
    web without a mail server anywhere in the story. Bound to the account rather than to an
    address, because a Telegram user may not have given us one — and resolving by address
    would sign them in as a *different* account, losing the player they have claimed.

    No cooldown, unlike the emailed kind. That one exists so the form cannot be used to fill
    a stranger's inbox; this link goes back to the person who asked for it.
    """
    raw, hashed = issue()
    await repositories.save(
        session,
        MagicLink(
            email="",
            account_id=account.id,
            token_hash=hashed,
            expires_at=utc_now() + MAGIC_LINK_TTL,
        ),
    )
    return raw


async def redeem_magic_link(session: AsyncSession, raw_token: str) -> Account:
    """Turn a link into an account, creating one on first sign-in."""
    link = await repositories.magic_link_by_token(session, hash_token(raw_token))
    if link is None or link.used_at is not None:
        raise InvalidTokenError("this link is not valid — ask for a new one")
    if link.expires_at <= utc_now():
        raise TokenExpiredError("this link has expired — ask for a new one")

    link.used_at = utc_now()
    await session.flush()

    if link.account_id is not None:
        bound = await repositories.account_by_id(session, link.account_id)
        if bound is None:  # pragma: no cover - the foreign key cascades
            raise InvalidTokenError("this link is not valid — ask for a new one")
        return bound
    return await ensure_identity(session, PROVIDER_EMAIL, link.email)


# ----------------------------------------------------------------------------- sessions


async def open_session(session: AsyncSession, account: Account) -> str:
    """Start a signed-in session and return the token for the cookie."""
    now = utc_now()
    await repositories.purge_dead_sessions(
        session, expired_before=now, idle_since=now - SESSION_IDLE_TTL
    )

    raw, hashed = issue()
    await repositories.save(
        session,
        LoginSession(
            account_id=account.id,
            token_hash=hashed,
            expires_at=now + SESSION_TTL,
            last_used_at=now,
        ),
    )
    return raw


def _is_live(row: LoginSession, now: datetime) -> bool:
    """Both deadlines, and a session has to clear both."""
    return row.expires_at > now and row.last_used_at > now - SESSION_IDLE_TTL


async def account_for_session(session: AsyncSession, raw_token: str) -> Account | None:
    """Who is signed in, if anyone. A session past either deadline is nobody.

    Reading also counts as using, so this writes — rarely. See :data:`TOUCH_AFTER`.
    """
    row = await repositories.login_session_by_token(session, hash_token(raw_token))
    now = utc_now()
    if row is None or not _is_live(row, now):
        return None

    if now - row.last_used_at > TOUCH_AFTER:
        row.last_used_at = now
        await session.flush()

    return await repositories.account_by_id(session, row.account_id)


async def close_session(session: AsyncSession, raw_token: str) -> None:
    """Sign out. Unknown tokens are not an error — the outcome is the one asked for."""
    row = await repositories.login_session_by_token(session, hash_token(raw_token))
    if row is not None:
        await repositories.revoke(session, row)


async def close_all_sessions(session: AsyncSession, account: Account) -> None:
    """Sign out everywhere. The reason sessions are rows rather than signed tokens."""
    rows = await repositories.sessions_of(session, account.id)
    for row in rows:
        await repositories.revoke(session, row)
