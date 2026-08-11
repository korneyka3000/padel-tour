"""Invitations: how a person becomes a particular player.

No integration can do this on its own. A bot knows it is talking to a stable human; it does
not know that human is the player called "Аня". Somebody has to say so, and that somebody is
the group's owner.

The invitation is issued against **one player**, which is what makes claiming someone else's
history impossible. How it is accepted — in a browser after an email link, or by tapping it
inside a chat — is a detail of whichever integration the person happens to use.
"""

from __future__ import annotations

from datetime import timedelta
from typing import TYPE_CHECKING

from sqlalchemy import select

from padel_tour.db import Invite, Player, utc_now

from .errors import (
    AlreadyPlayingHereError,
    ForbiddenError,
    InviteNotFoundError,
    InviteUsedError,
    PlayerAlreadyClaimedError,
    PlayerNotFoundError,
)
from .permissions import require_owner
from .tokens import hash_token, issue
from .views import PlayerView

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account

#: Long enough to reach someone who plays weekly, short enough that a forgotten link in a
#: chat does not stay live forever.
INVITE_TTL = timedelta(days=7)


def _to_view(player: Player) -> PlayerView:
    return PlayerView(
        id=player.id,
        group_id=player.group_id,
        name=player.name,
        is_active=player.is_active,
    )


async def create_invite(session: AsyncSession, actor: Account | None, player_id: uuid.UUID) -> str:
    """Issue an invitation for one player. Returns the token to hand out."""
    player = await session.get(Player, player_id)
    if player is None:
        raise PlayerNotFoundError(f"no player with id {player_id}")
    await require_owner(session, actor, player.group_id)

    if player.account_id is not None:
        raise PlayerAlreadyClaimedError(f"{player.name} is already claimed", name=player.name)

    raw, hashed = issue()
    session.add(
        Invite(
            player_id=player.id,
            created_by_account_id=actor.id if actor is not None else None,
            token_hash=hashed,
            expires_at=utc_now() + INVITE_TTL,
        )
    )
    await session.flush()
    return raw


async def peek_invite(session: AsyncSession, raw_token: str) -> PlayerView:
    """Who this invitation is for, without accepting it.

    Lets a page say "join as Аня" before asking anyone to sign in.
    """
    invite, player = await _load(session, raw_token)
    _ = invite
    return _to_view(player)


async def redeem_invite(session: AsyncSession, raw_token: str, account: Account) -> PlayerView:
    """Bind an account to the player this invitation names."""
    invite, player = await _load(session, raw_token)
    bind(player, account, await _other_player_of(session, player, account))
    invite.used_at = utc_now()
    await session.flush()
    return _to_view(player)


async def claim_player(session: AsyncSession, player_id: uuid.UUID, account: Account) -> PlayerView:
    """Say "that one is me", with no invitation in between.

    An invitation exists so that somebody who can be reached out of band vouches for the
    match between a person and a name. Inside a chat that ceremony has no content: the group
    is the membership list, everybody in it can see who tapped, and the same people could
    issue each other invitations anyway — a chat group has no owner, so ``require_owner``
    lets any of them through.

    What it does keep are the two guards that matter. A player already spoken for cannot be
    taken, and nobody plays as two people in one group.
    """
    player = await session.get(Player, player_id)
    if player is None:
        raise PlayerNotFoundError("that player no longer exists")
    bind(player, account, await _other_player_of(session, player, account))
    await session.flush()
    return _to_view(player)


async def release_player(
    session: AsyncSession, player_id: uuid.UUID, account: Account
) -> PlayerView:
    """Let go of a player you hold.

    The other half of claiming one by tapping. Without it a mistap is permanent, and a
    permanent mistake attached to somebody else's history is the reason a confirmation step
    would otherwise be needed on every claim.
    """
    player = await session.get(Player, player_id)
    if player is None:
        raise PlayerNotFoundError("that player no longer exists")
    if player.account_id != account.id:
        raise ForbiddenError("you are not playing as this player")

    player.account_id = None
    await session.flush()
    return _to_view(player)


def bind(player: Player, account: Account, other: Player | None) -> None:
    """Attach an account to a player, or explain why not."""
    if player.account_id is not None:
        raise PlayerAlreadyClaimedError(f"{player.name} is already claimed", name=player.name)
    if other is not None:
        raise AlreadyPlayingHereError(
            f"in this group you already play as {other.name}", name=other.name
        )
    player.account_id = account.id


async def _other_player_of(
    session: AsyncSession, player: Player, account: Account
) -> Player | None:
    """Whoever this account already is in this group, if anyone."""
    return await session.scalar(
        select(Player).where(
            Player.group_id == player.group_id,
            Player.account_id == account.id,
            Player.id != player.id,
        )
    )


async def _load(session: AsyncSession, raw_token: str) -> tuple[Invite, Player]:
    invite = await session.scalar(select(Invite).where(Invite.token_hash == hash_token(raw_token)))
    if invite is None:
        raise InviteNotFoundError("no such invitation")
    if invite.used_at is not None:
        raise InviteUsedError("this invitation has already been accepted")
    if invite.expires_at <= utc_now():
        raise InviteNotFoundError("this invitation has expired — ask for a new one")

    player = await session.get(Player, invite.player_id)
    if player is None:  # pragma: no cover - the foreign key prevents it
        raise PlayerNotFoundError("that player no longer exists")
    return invite, player
