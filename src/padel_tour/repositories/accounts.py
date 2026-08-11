"""Accounts, the identities that reach them, and the tokens that open a session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from padel_tour.db import Account, Identity, LoginSession, MagicLink

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence
    from datetime import datetime

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.orm import DeclarativeBase


async def save[T: DeclarativeBase](session: AsyncSession, row: T) -> T:
    """Add a row and flush, so its generated id is readable straight away.

    Flushed, not committed. The transaction belongs to whoever opened it — the middleware
    for a bot update, the dependency for a request — and a repository that committed would
    be a second opinion about where a unit of work ends.
    """
    session.add(row)
    await session.flush()
    return row


async def account_by_id(session: AsyncSession, account_id: uuid.UUID) -> Account | None:
    return await session.get(Account, account_id)


async def account_by_identity(
    session: AsyncSession, provider: str, external_id: str
) -> Account | None:
    """The account behind an external login."""
    return await session.scalar(
        select(Account)
        .join(Identity, Identity.account_id == Account.id)
        .where(Identity.provider == provider, Identity.external_id == external_id)
    )


async def add_identity(
    session: AsyncSession, account: Account, provider: str, external_id: str
) -> Identity:
    return await save(
        session, Identity(account_id=account.id, provider=provider, external_id=external_id)
    )


async def external_ids_of(
    session: AsyncSession, account_id: uuid.UUID, provider: str
) -> Sequence[str]:
    """Every external id this account signs in with, for one provider."""
    return list(
        await session.scalars(
            select(Identity.external_id).where(
                Identity.account_id == account_id, Identity.provider == provider
            )
        )
    )


async def recent_magic_link(
    session: AsyncSession, email: str, *, since: datetime
) -> MagicLink | None:
    """A link already on its way to this address, if one is."""
    return await session.scalar(
        select(MagicLink).where(MagicLink.email == email, MagicLink.created_at > since).limit(1)
    )


async def magic_link_by_token(session: AsyncSession, token_hash: str) -> MagicLink | None:
    return await session.scalar(select(MagicLink).where(MagicLink.token_hash == token_hash))


async def login_session_by_token(session: AsyncSession, token_hash: str) -> LoginSession | None:
    return await session.scalar(select(LoginSession).where(LoginSession.token_hash == token_hash))


async def sessions_of(session: AsyncSession, account_id: uuid.UUID) -> Sequence[LoginSession]:
    """Every live session for an account. Revoking them is the caller's business."""
    return list(
        await session.scalars(select(LoginSession).where(LoginSession.account_id == account_id))
    )


async def revoke(session: AsyncSession, row: LoginSession) -> None:
    """Delete one sign-in session. Flushed, not committed — see :func:`save`."""
    await session.delete(row)
    await session.flush()
