"""Groups and their players."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, or_, select

from padel_tour.db import Group, GroupLink, Player

from .errors import (
    DuplicateGroupNameError,
    DuplicatePlayerNameError,
    GroupNotFoundError,
    PlayerNotFoundError,
)
from .permissions import require_owner
from .views import GroupView, PlayerView

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account


def _to_group_view(group: Group, player_count: int) -> GroupView:
    return GroupView(
        id=group.id,
        name=group.name,
        owner_account_id=group.owner_account_id,
        player_count=player_count,
    )


def _to_player_view(player: Player) -> PlayerView:
    return PlayerView(
        id=player.id,
        group_id=player.group_id,
        name=player.name,
        is_active=player.is_active,
    )


async def get_group(session: AsyncSession, group_id: uuid.UUID) -> Group:
    """Fetch a group row or raise. Internal helper other services build on."""
    group = await session.get(Group, group_id)
    if group is None:
        raise GroupNotFoundError(f"no group with id {group_id}")
    return group


async def create_group(
    session: AsyncSession, name: str, *, owner_account_id: uuid.UUID | None = None
) -> GroupView:
    """Register a new group.

    Uniqueness is checked here for a readable error, and enforced by the database for
    correctness — two concurrent creates would otherwise both pass the check.
    """
    clean = name.strip()
    existing = await session.scalar(select(Group).where(Group.name == clean))
    if existing is not None:
        raise DuplicateGroupNameError(f"a group called {clean!r} already exists")

    group = Group(name=clean, owner_account_id=owner_account_id)
    session.add(group)
    await session.flush()
    return _to_group_view(group, player_count=0)


async def list_groups(session: AsyncSession) -> list[GroupView]:
    """Every group, with how many active players each has."""
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
    return [_to_group_view(group, total) for group, total in rows]


async def groups_for_account(session: AsyncSession, account: Account) -> list[GroupView]:
    """The groups this account belongs to — as a player, or as the owner.

    An owner who has not claimed a player of their own still belongs to their group, which
    is why this is two conditions rather than one join.
    """
    mine = select(Player.group_id).where(Player.account_id == account.id)
    ids = set(
        await session.scalars(
            select(Group.id).where(
                or_(Group.owner_account_id == account.id, Group.id.in_(mine)),
            )
        )
    )
    return [group for group in await list_groups(session) if group.id in ids]


async def group_for_link(
    session: AsyncSession, provider: str, external_id: str
) -> GroupView | None:
    """The group reachable through an external place — a chat, say.

    Takes a provider rather than naming one, so the service layer stays ignorant of which
    integrations exist.
    """
    group = await session.scalar(
        select(Group)
        .join(GroupLink, GroupLink.group_id == Group.id)
        .where(GroupLink.provider == provider, GroupLink.external_id == external_id)
    )
    if group is None:
        return None
    total = await session.scalar(
        select(func.count(Player.id)).where(Player.group_id == group.id, Player.is_active)
    )
    return _to_group_view(group, total or 0)


async def link_group(
    session: AsyncSession, group_id: uuid.UUID, provider: str, external_id: str
) -> GroupView:
    """Make a group reachable from an external place."""
    group = await get_group(session, group_id)
    session.add(GroupLink(group_id=group_id, provider=provider, external_id=external_id))
    await session.flush()
    total = await session.scalar(
        select(func.count(Player.id)).where(Player.group_id == group.id, Player.is_active)
    )
    return _to_group_view(group, total or 0)


async def get_player(session: AsyncSession, player_id: uuid.UUID) -> Player:
    """Fetch a player row or raise."""
    player = await session.get(Player, player_id)
    if player is None:
        raise PlayerNotFoundError(f"no player with id {player_id}")
    return player


async def add_player(
    session: AsyncSession,
    group_id: uuid.UUID,
    name: str,
    *,
    actor: Account | None = None,
) -> PlayerView:
    """Add a player to a group.

    Re-adding someone who was deactivated reactivates them rather than failing: from the
    organiser's point of view that is obviously what 'add Ann' means when Ann used to play
    here, and it keeps her history attached.
    """
    await get_group(session, group_id)
    await require_owner(session, actor, group_id)
    clean = name.strip()

    existing = await session.scalar(
        select(Player).where(Player.group_id == group_id, Player.name == clean)
    )
    if existing is not None:
        if existing.is_active:
            raise DuplicatePlayerNameError(f"{clean!r} is already in this group")
        existing.is_active = True
        await session.flush()
        return _to_player_view(existing)

    player = Player(group_id=group_id, name=clean)
    session.add(player)
    await session.flush()
    return _to_player_view(player)


async def list_players(
    session: AsyncSession, group_id: uuid.UUID, *, include_inactive: bool = False
) -> list[PlayerView]:
    """Players of a group, by name."""
    await get_group(session, group_id)
    query = select(Player).where(Player.group_id == group_id)
    if not include_inactive:
        query = query.where(Player.is_active)
    players = await session.scalars(query.order_by(Player.name))
    return [_to_player_view(player) for player in players]


async def rename_player(
    session: AsyncSession,
    player_id: uuid.UUID,
    name: str,
    *,
    actor: Account | None = None,
) -> PlayerView:
    """Rename a player. Their tournament history is untouched — it stores ids, not names."""
    player = await get_player(session, player_id)
    await require_owner(session, actor, player.group_id)
    clean = name.strip()

    clash = await session.scalar(
        select(Player).where(
            Player.group_id == player.group_id,
            Player.name == clean,
            Player.id != player.id,
        )
    )
    if clash is not None:
        raise DuplicatePlayerNameError(f"{clean!r} is already in this group")

    player.name = clean
    await session.flush()
    return _to_player_view(player)


async def deactivate_player(
    session: AsyncSession, player_id: uuid.UUID, *, actor: Account | None = None
) -> PlayerView:
    """Retire a player from the roster without erasing them from past tournaments."""
    player = await get_player(session, player_id)
    await require_owner(session, actor, player.group_id)
    player.is_active = False
    await session.flush()
    return _to_player_view(player)
