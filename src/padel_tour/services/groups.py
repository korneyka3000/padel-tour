"""Groups and their players."""

from __future__ import annotations

from typing import TYPE_CHECKING

from padel_tour import repositories
from padel_tour.db import Group, GroupLink, Player

from .errors import (
    DuplicateGroupNameError,
    DuplicatePlayerNameError,
    GroupNotFoundError,
    PlayerNotFoundError,
)
from .permissions import is_admin, require_owner
from .views import GroupView, PlayerView

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account


def _to_group_view(group: Group, player_count: int) -> GroupView:
    """The row plus the one thing that is not on it."""
    return GroupView.model_validate(group).model_copy(update={"player_count": player_count})


async def get_group(session: AsyncSession, group_id: uuid.UUID) -> Group:
    """Fetch a group row or raise. Internal helper other services build on."""
    group = await repositories.group_by_id(session, group_id)
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
    existing = await repositories.group_by_name(session, clean)
    if existing is not None:
        raise DuplicateGroupNameError(f"a group called {clean!r} already exists")

    group = await repositories.save(session, Group(name=clean, owner_account_id=owner_account_id))
    return _to_group_view(group, player_count=0)


async def list_groups(session: AsyncSession) -> list[GroupView]:
    """Every group, with how many active players each has."""
    return [
        _to_group_view(group, total)
        for group, total in await repositories.groups_with_counts(session)
    ]


async def groups_for_account(session: AsyncSession, account: Account) -> list[GroupView]:
    """The groups this account belongs to — as a player, or as the owner.

    An owner who has not claimed a player of their own still belongs to their group, which
    is why this is two conditions rather than one join.

    An admin sees all of them. Not a shortcut: the list is supposed to answer "what can I
    open", and for an admin the answer is everything — a list narrower than the permission
    rule sends somebody to hunt for a URL they are already allowed to visit.
    """
    if await is_admin(session, account):
        return await list_groups(session)

    ids = await repositories.group_ids_for_account(session, account)
    return [group for group in await list_groups(session) if group.id in ids]


async def group_for_link(
    session: AsyncSession, provider: str, external_id: str
) -> GroupView | None:
    """The group reachable through an external place — a chat, say.

    Takes a provider rather than naming one, so the service layer stays ignorant of which
    integrations exist.
    """
    group = await repositories.group_by_link(session, provider, external_id)
    if group is None:
        return None
    return _to_group_view(group, await repositories.active_player_count(session, group.id))


async def link_group(
    session: AsyncSession, group_id: uuid.UUID, provider: str, external_id: str
) -> GroupView:
    """Make a group reachable from an external place."""
    group = await get_group(session, group_id)
    await repositories.save(
        session, GroupLink(group_id=group_id, provider=provider, external_id=external_id)
    )
    return _to_group_view(group, await repositories.active_player_count(session, group.id))


async def get_player(session: AsyncSession, player_id: uuid.UUID) -> Player:
    """Fetch a player row or raise."""
    player = await repositories.player_by_id(session, player_id)
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

    existing = await repositories.player_by_name(session, group_id, clean)
    if existing is not None:
        if existing.is_active:
            raise DuplicatePlayerNameError(f"{clean!r} is already in this group")
        existing.is_active = True
        await session.flush()
        return PlayerView.model_validate(existing)

    player = await repositories.save(session, Player(group_id=group_id, name=clean))
    return PlayerView.model_validate(player)


async def list_players(
    session: AsyncSession, group_id: uuid.UUID, *, include_inactive: bool = False
) -> list[PlayerView]:
    """Players of a group, by name."""
    await get_group(session, group_id)
    players = await repositories.players_of_group(
        session, group_id, include_inactive=include_inactive
    )
    return [PlayerView.model_validate(player) for player in players]


async def player_for_account(
    session: AsyncSession, group_id: uuid.UUID, account: Account
) -> PlayerView | None:
    """Which player in this group this account holds, if any.

    The question every personal view starts from: matches are recorded against a player, so
    "my statistics" is really "the statistics of whichever player is me here".
    """
    player = await repositories.player_of_account(session, group_id, account.id)
    return None if player is None else PlayerView.model_validate(player)


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

    clash = await repositories.player_by_name(session, player.group_id, clean, other_than=player.id)
    if clash is not None:
        raise DuplicatePlayerNameError(f"{clean!r} is already in this group")

    player.name = clean
    await session.flush()
    return PlayerView.model_validate(player)


async def deactivate_player(
    session: AsyncSession, player_id: uuid.UUID, *, actor: Account | None = None
) -> PlayerView:
    """Retire a player from the roster without erasing them from past tournaments."""
    player = await get_player(session, player_id)
    await require_owner(session, actor, player.group_id)
    player.is_active = False
    await session.flush()
    return PlayerView.model_validate(player)
