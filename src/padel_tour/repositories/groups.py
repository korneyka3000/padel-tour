"""Groups, the people in them, and how a chat reaches one."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select

from padel_tour.db import Group, GroupLink, Player

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account


async def group_by_id(session: AsyncSession, group_id: uuid.UUID) -> Group | None:
    return await session.get(Group, group_id)


async def group_by_name(session: AsyncSession, name: str) -> Group | None:
    return await session.scalar(select(Group).where(Group.name == name))


async def group_by_link(session: AsyncSession, provider: str, external_id: str) -> Group | None:
    """The group a chat — or any other outside place — points at."""
    return await session.scalar(
        select(Group)
        .join(GroupLink, GroupLink.group_id == Group.id)
        .where(GroupLink.provider == provider, GroupLink.external_id == external_id)
    )


async def groups_with_counts(session: AsyncSession) -> Sequence[tuple[Group, int]]:
    """Every group with how many active players it has.

    One query with a subquery rather than a count per group: the second shape is an N+1 that
    only shows itself once somebody has a dozen groups.
    """
    counts = (
        select(Player.group_id, func.count(Player.id).label("total"))
        .where(Player.is_active)
        .group_by(Player.group_id)
        .subquery()
    )
    rows = await session.execute(
        select(Group, func.coalesce(counts.c.total, 0))
        .outerjoin(counts, counts.c.group_id == Group.id)
        .order_by(Group.name)
    )
    return [(group, int(total)) for group, total in rows.all()]


async def group_ids_for_account(session: AsyncSession, account: Account) -> set[uuid.UUID]:
    """Groups this account owns or plays in.

    Two conditions rather than one join: an owner who has never claimed a player of their
    own still belongs to their group.
    """
    mine = select(Player.group_id).where(Player.account_id == account.id)
    return set(
        await session.scalars(
            select(Group.id).where(or_(Group.owner_account_id == account.id, Group.id.in_(mine)))
        )
    )


async def active_player_count(session: AsyncSession, group_id: uuid.UUID) -> int:
    total = await session.scalar(
        select(func.count(Player.id)).where(Player.group_id == group_id, Player.is_active)
    )
    return int(total or 0)


async def player_by_id(session: AsyncSession, player_id: uuid.UUID) -> Player | None:
    return await session.get(Player, player_id)


async def player_by_name(
    session: AsyncSession, group_id: uuid.UUID, name: str, *, other_than: uuid.UUID | None = None
) -> Player | None:
    """Somebody in this group already called that, for deciding whether a name is free.

    ``other_than`` excludes the player being renamed, who is allowed to keep their own name.
    """
    query = select(Player).where(Player.group_id == group_id, Player.name == name)
    if other_than is not None:
        query = query.where(Player.id != other_than)
    return await session.scalar(query)


async def player_of_account(
    session: AsyncSession, group_id: uuid.UUID, account_id: uuid.UUID
) -> Player | None:
    """Which player in this group an account holds, if any."""
    return await session.scalar(
        select(Player).where(Player.group_id == group_id, Player.account_id == account_id)
    )


async def players_of_group(
    session: AsyncSession, group_id: uuid.UUID, *, include_inactive: bool = False
) -> Sequence[Player]:
    query = select(Player).where(Player.group_id == group_id)
    if not include_inactive:
        query = query.where(Player.is_active)
    return list(await session.scalars(query.order_by(Player.name)))


async def players_by_ids(
    session: AsyncSession, player_ids: Sequence[uuid.UUID]
) -> Sequence[Player]:
    return list(await session.scalars(select(Player).where(Player.id.in_(player_ids))))
