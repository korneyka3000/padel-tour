"""Who is allowed to do what.

Two levels, because that is how a padel group actually works. A **group owner** keeps the
roster and hands out invitations. A **tournament organiser** runs one tournament — the role
belongs to the tournament, not the group, since last week it was one person and this week
another.

Scoring is deliberately wider than organising: on court the phone belongs to whoever is
nearest, so any of the four who played a match may enter its result. Ending or redrawing
takes the game away from everyone else, so those stay with the organiser.

Checks live here and are called from the service functions they guard, not from a decorator
on a route — the bot calls those functions directly and must not be able to skip them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from padel_tour.db import Group, Player, Tournament, TournamentPlayer

from .errors import ForbiddenError, GroupNotFoundError, TournamentNotFoundError

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account

#: A caller with no account: the CLI, a migration, a test fixture. Trusted, because it is
#: us. Everything reaching the outside world passes a real account.
System = None


async def is_member(session: AsyncSession, actor: Account, group_id: uuid.UUID) -> bool:
    """Does this account play in this group?"""
    player = await session.scalar(
        select(Player.id).where(Player.group_id == group_id, Player.account_id == actor.id)
    )
    if player is not None:
        return True
    # An owner who has not claimed a player of their own still belongs here.
    owner = await session.scalar(
        select(Group.id).where(Group.id == group_id, Group.owner_account_id == actor.id)
    )
    return owner is not None


async def require_member(session: AsyncSession, actor: Account | None, group_id: uuid.UUID) -> None:
    if actor is System:
        return
    group = await session.get(Group, group_id)
    if group is None:
        raise GroupNotFoundError(f"no group with id {group_id}")
    # A group nobody owns — made from the CLI, or before owners existed — is open. Locking
    # it to nobody would strand the people already in it.
    if group.owner_account_id is None:
        return
    if not await is_member(session, actor, group_id):
        raise ForbiddenError("Вы не состоите в этой группе")


async def require_owner(session: AsyncSession, actor: Account | None, group_id: uuid.UUID) -> None:
    if actor is System:
        return
    group = await session.get(Group, group_id)
    if group is None:
        raise GroupNotFoundError(f"no group with id {group_id}")
    # A group made before owners existed, or from the CLI, has none. Leaving it open is
    # better than locking it to nobody.
    if group.owner_account_id is None:
        return
    if group.owner_account_id != actor.id:
        raise ForbiddenError("Это может сделать только владелец группы")


async def require_organiser(
    session: AsyncSession, actor: Account | None, tournament_id: uuid.UUID
) -> None:
    """The organiser, or the group's owner if the organiser walked off with the phone."""
    if actor is System:
        return
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise TournamentNotFoundError(f"no tournament with id {tournament_id}")
    if tournament.organiser_account_id is None:
        return
    if tournament.organiser_account_id == actor.id:
        return

    group = await session.get(Group, tournament.group_id)
    if group is not None and group.owner_account_id == actor.id:
        return
    raise ForbiddenError("Это может сделать только тот, кто начал турнир")


async def require_can_score(
    session: AsyncSession,
    actor: Account | None,
    tournament_id: uuid.UUID,
    players_on_court: set[uuid.UUID],
) -> None:
    """Anyone who played this match, plus the organiser.

    Nobody waits for the organiser to come back from the water fountain — on court the phone
    belongs to whoever is nearest.

    The check only bites against someone we can actually name. Claiming a player is opt-in:
    until an invitation is accepted we cannot tell a participant from a bystander, and
    refusing everyone would break the bot in exactly the setting it was built for. The moment
    an account *is* known to be a player who was not on that court, it is refused. Protection
    against a wrong score is confirmation by the other pair, not this check.
    """
    if actor is System:
        return

    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise TournamentNotFoundError(f"no tournament with id {tournament_id}")
    await require_member(session, actor, tournament.group_id)
    if tournament.organiser_account_id is None or tournament.organiser_account_id == actor.id:
        return

    plays_as = await session.scalar(
        select(Player.id)
        .join(TournamentPlayer, TournamentPlayer.player_id == Player.id)
        .where(TournamentPlayer.tournament_id == tournament_id, Player.account_id == actor.id)
    )
    if plays_as is None:
        return
    if plays_as not in players_on_court:
        raise ForbiddenError("Счёт вносит тот, кто играл этот матч, или организатор")
