"""Accounts, the identities that reach them, and the tokens that open a session."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import delete, func, select

from padel_tour.db import Account, Identity, LoginSession, MagicLink, Player

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection, Sequence
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


async def purge_dead_sessions(
    session: AsyncSession, *, expired_before: datetime, idle_since: datetime
) -> None:
    """Drop every session past either of its two deadlines, whoever it belonged to.

    Both cut-offs are arguments rather than constants here: *how long* is policy, and policy
    lives in the service. This only knows that there are two ways for a session to be over.

    Not tidiness. The table is the answer to "where can this person still be signed in", and
    an answer padded with dead rows is not one. Called when a session opens rather than on a
    schedule, because sign-ins are rare, both columns are cheap to scan at this size, and a
    cron job is one more thing that can quietly stop running.
    """
    await session.execute(
        delete(LoginSession).where(
            (LoginSession.expires_at < expired_before) | (LoginSession.last_used_at < idle_since)
        )
    )
    await session.flush()


async def all_accounts(session: AsyncSession, *, limit: int, offset: int) -> Sequence[Account]:
    """Every account, newest first. The admin list, and nothing else asks for this."""
    return list(
        await session.scalars(
            select(Account).order_by(Account.created_at.desc()).limit(limit).offset(offset)
        )
    )


async def identities_of(
    session: AsyncSession, account_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, list[tuple[str, str]]]:
    """Every way in, for a set of accounts, in one query.

    Grouped here rather than by a relationship per row: the admin list shows twenty accounts
    at a time and reading `account.identities` on each is the N+1 this layer exists to stop.
    """
    if not account_ids:
        return {}
    rows = await session.execute(
        select(Identity.account_id, Identity.provider, Identity.external_id)
        .where(Identity.account_id.in_(account_ids))
        .order_by(Identity.provider)
    )
    found: dict[uuid.UUID, list[tuple[str, str]]] = {}
    for account_id, provider, external in rows:
        found.setdefault(account_id, []).append((provider, external))
    return found


async def last_seen_of(
    session: AsyncSession, account_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, datetime]:
    """When each account last used a live session.

    Only sessions that still exist, so somebody who signed out everywhere reads as unknown
    rather than as long gone. That is the honest answer: we deleted the evidence.
    """
    if not account_ids:
        return {}
    rows = await session.execute(
        select(LoginSession.account_id, func.max(LoginSession.last_used_at))
        .where(LoginSession.account_id.in_(account_ids))
        .group_by(LoginSession.account_id)
    )
    return {row.account_id: row[1] for row in rows}


async def count_accounts(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(Account.id))) or 0)


async def players_of_accounts(
    session: AsyncSession, account_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, list[str]]:
    """The players each account holds, by name, in one query.

    Names rather than ids because the only caller is a screen listing people, and an admin
    scanning for "who is Аня here" cannot do it from a column of UUIDs.
    """
    if not account_ids:
        return {}
    rows = await session.execute(
        select(Player.account_id, Player.name)
        .where(Player.account_id.in_(account_ids))
        .order_by(Player.name)
    )
    found: dict[uuid.UUID, list[str]] = {}
    for account_id, name in rows:
        found.setdefault(account_id, []).append(name)
    return found
