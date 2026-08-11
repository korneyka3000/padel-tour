"""Invitations, and the one question claiming a player has to ask first."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from padel_tour.db import Invite, Player

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account


async def invite_by_token(session: AsyncSession, token_hash: str) -> Invite | None:
    return await session.scalar(select(Invite).where(Invite.token_hash == token_hash))


async def other_player_of_account(
    session: AsyncSession, player: Player, account: Account
) -> Player | None:
    """Whoever this account already is in this group, if not the player in hand.

    The question behind "nobody plays as two people in one group", asked before a claim
    rather than discovered by a unique index afterwards — the index is the backstop, and its
    error message is for us, not for a person.
    """
    return await session.scalar(
        select(Player).where(
            Player.group_id == player.group_id,
            Player.account_id == account.id,
            Player.id != player.id,
        )
    )
