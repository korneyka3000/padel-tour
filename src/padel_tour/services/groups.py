"""Groups and their players."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from padel_tour.db import Group, Player

from .errors import (
    DuplicateGroupNameError,
    DuplicatePlayerNameError,
    GroupNotFoundError,
    PlayerNotFoundError,
)
from .views import GroupView, PlayerView

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession


def _to_group_view(group: Group, player_count: int) -> GroupView:
    return GroupView(
        id=group.id,
        name=group.name,
        telegram_chat_id=group.telegram_chat_id,
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
    session: AsyncSession, name: str, *, telegram_chat_id: int | None = None
) -> GroupView:
    """Register a new group.

    Uniqueness is checked here for a readable error, and enforced by the database for
    correctness — two concurrent creates would otherwise both pass the check.
    """
    clean = name.strip()
    existing = await session.scalar(select(Group).where(Group.name == clean))
    if existing is not None:
        raise DuplicateGroupNameError(f"a group called {clean!r} already exists")

    group = Group(name=clean, telegram_chat_id=telegram_chat_id)
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


async def group_by_chat(session: AsyncSession, telegram_chat_id: int) -> GroupView | None:
    """Find the group bound to a Telegram chat, if any. Used by the bot in M3."""
    group = await session.scalar(select(Group).where(Group.telegram_chat_id == telegram_chat_id))
    if group is None:
        return None
    total = await session.scalar(
        select(func.count(Player.id)).where(Player.group_id == group.id, Player.is_active)
    )
    return _to_group_view(group, total or 0)


async def bind_group_to_chat(
    session: AsyncSession, group_id: uuid.UUID, telegram_chat_id: int
) -> GroupView:
    """Attach a group to a Telegram chat so the bot can find it."""
    group = await get_group(session, group_id)
    group.telegram_chat_id = telegram_chat_id
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


async def add_player(session: AsyncSession, group_id: uuid.UUID, name: str) -> PlayerView:
    """Add a player to a group.

    Re-adding someone who was deactivated reactivates them rather than failing: from the
    organiser's point of view that is obviously what 'add Ann' means when Ann used to play
    here, and it keeps her history attached.
    """
    await get_group(session, group_id)
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


async def rename_player(session: AsyncSession, player_id: uuid.UUID, name: str) -> PlayerView:
    """Rename a player. Their tournament history is untouched — it stores ids, not names."""
    player = await get_player(session, player_id)
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


async def deactivate_player(session: AsyncSession, player_id: uuid.UUID) -> PlayerView:
    """Retire a player from the roster without erasing them from past tournaments."""
    player = await get_player(session, player_id)
    player.is_active = False
    await session.flush()
    return _to_player_view(player)
