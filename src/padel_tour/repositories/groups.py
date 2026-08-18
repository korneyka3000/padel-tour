"""Groups, the people in them, and how a chat reaches one."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select

from padel_tour.db import Group, GroupLink, Player, Tournament

if TYPE_CHECKING:
    import uuid
    from collections.abc import Collection, Sequence

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


async def group_names(
    session: AsyncSession, group_ids: Collection[uuid.UUID]
) -> dict[uuid.UUID, str]:
    """Names for a set of groups, in one query.

    For lists that span groups. The alternative is a relationship read per row, which is the
    N+1 this layer exists to prevent — a page of twenty tournaments would be twenty queries
    to print twenty words.
    """
    if not group_ids:
        return {}
    rows = await session.execute(select(Group.id, Group.name).where(Group.id.in_(group_ids)))
    return {row.id: row.name for row in rows}


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


async def counts_under(session: AsyncSession, group_id: uuid.UUID) -> tuple[int, int]:
    """How many players and tournaments a group is holding up.

    For the confirmation before a delete. The foreign keys cascade, so removing a group
    silently takes its roster and every tournament it ever played with it — a screen that
    does not say so is asking for a yes to a question nobody was shown.
    """
    players = await session.scalar(select(func.count(Player.id)).where(Player.group_id == group_id))
    tournaments = await session.scalar(
        select(func.count(Tournament.id)).where(Tournament.group_id == group_id)
    )
    return int(players or 0), int(tournaments or 0)


async def drop_group(session: AsyncSession, group: Group) -> None:
    """Delete a group. Everything under it goes too — see :func:`counts_under`."""
    await session.delete(group)
    await session.flush()


async def count_groups(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(Group.id))) or 0)


async def count_players(session: AsyncSession) -> int:
    return int(await session.scalar(select(func.count(Player.id))) or 0)
