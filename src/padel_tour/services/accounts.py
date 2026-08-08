"""Accounts: who a person is to us, and how they arrive.

An `Account` carries no provider-specific field. Signing in with an email, pressing a button
in Telegram, or anything added later are rows in `identities` — so a new integration never
reshapes the domain, and this module never learns the name of one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from padel_tour.db import Account, Identity

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


async def get_account(session: AsyncSession, account_id: uuid.UUID) -> Account | None:
    return await session.get(Account, account_id)


async def account_for_identity(
    session: AsyncSession, provider: str, external_id: str
) -> Account | None:
    """The account behind one external login, if we have seen it before."""
    return await session.scalar(
        select(Account)
        .join(Identity, Identity.account_id == Account.id)
        .where(Identity.provider == provider, Identity.external_id == external_id)
    )


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
        return existing

    account = Account(display_name=display_name)
    session.add(account)
    await session.flush()
    session.add(Identity(account_id=account.id, provider=provider, external_id=external_id))
    await session.flush()
    return account


async def attach_identity(
    session: AsyncSession, account: Account, provider: str, external_id: str
) -> None:
    """Add another way of signing in to an account that already exists."""
    session.add(Identity(account_id=account.id, provider=provider, external_id=external_id))
    await session.flush()
