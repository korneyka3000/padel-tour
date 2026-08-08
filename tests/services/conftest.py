"""Shared scaffolding for service tests that need people and a group.

Building a group with an owner, a roster and claimed players takes half a dozen calls, and
the permission tests each need a slightly different arrangement of them. This assembles the
whole thing in one call so a test can spend its lines on what it is actually asserting.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from padel_tour.db import PROVIDER_EMAIL, Player
from padel_tour.services import (
    add_player,
    create_group,
    ensure_identity,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account

NAMES = ("Аня", "Боря", "Вика", "Гриша", "Даша", "Егор", "Жанна", "Зина")


@dataclass(frozen=True, slots=True)
class Club:
    """A group with an owner and eight people on the roster."""

    group_id: uuid.UUID
    owner: Account
    players: tuple[uuid.UUID, ...]

    def player(self, name: str) -> uuid.UUID:
        return self.players[NAMES.index(name)]


async def account(session: AsyncSession, address: str) -> Account:
    return await ensure_identity(session, PROVIDER_EMAIL, address)


async def make_club(session: AsyncSession, *, owned: bool = True) -> Club:
    """A ready-to-play group.

    ``owned=False`` gives the shape a chat or the CLI produces: nobody owns it, so the
    service layer leaves it open.
    """
    owner = await account(session, "owner@example.test")
    group = await create_group(
        session, "Вторничный падел", owner_account_id=owner.id if owned else None
    )
    players = [(await add_player(session, group.id, name, actor=owner)).id for name in NAMES]
    return Club(group_id=group.id, owner=owner, players=tuple(players))


async def claim(session: AsyncSession, player_id: uuid.UUID, holder: Account) -> None:
    """Bind a player to an account directly, for tests that are not about invitations."""
    player = await session.get(Player, player_id)
    assert player is not None
    player.account_id = holder.id
    await session.flush()
