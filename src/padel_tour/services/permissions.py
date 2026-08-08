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

from typing import TYPE_CHECKING, Final

from sqlalchemy import select

from padel_tour.db import Group, Player, Tournament, TournamentPlayer

from .errors import (
    ForbiddenError,
    GroupNotFoundError,
    NotSignedInError,
    TournamentNotFoundError,
)

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account


class Anonymous:
    """Nobody is signed in.

    Distinct from :data:`System` on purpose, and the distinction is the whole point. Both
    are "no account", but one is us and one is a stranger, and collapsing them into ``None``
    would mean every unauthenticated request arrived with the privileges of a migration.
    """

    __slots__ = ()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "ANONYMOUS"


#: A request that carries no account at all. Fails every check.
ANONYMOUS: Final = Anonymous()

#: A caller with no account *because it is us*: the CLI, a migration, a test fixture.
#: Trusted. Anything facing the outside world passes a real account or :data:`ANONYMOUS`.
System = None

#: Who is asking.
type Actor = "Account | Anonymous | None"


def _identified(actor: Actor) -> Account:
    """The account behind a check, or a refusal.

    Callers let :data:`System` through before reaching this, so anything still ``None`` here
    is a programming error rather than a stranger — and both are better refused than trusted.
    """
    if actor is None or isinstance(actor, Anonymous):
        raise NotSignedInError("Войдите, чтобы это увидеть")
    return actor


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


async def require_member(session: AsyncSession, actor: Actor, group_id: uuid.UUID) -> None:
    if actor is System:
        return
    account = _identified(actor)
    group = await session.get(Group, group_id)
    if group is None:
        raise GroupNotFoundError(f"no group with id {group_id}")
    # A group nobody owns — made from the CLI, or before owners existed — is open. Locking
    # it to nobody would strand the people already in it.
    if group.owner_account_id is None:
        return
    if not await is_member(session, account, group_id):
        raise ForbiddenError("Вы не состоите в этой группе")


async def require_owner(session: AsyncSession, actor: Actor, group_id: uuid.UUID) -> None:
    if actor is System:
        return
    account = _identified(actor)
    group = await session.get(Group, group_id)
    if group is None:
        raise GroupNotFoundError(f"no group with id {group_id}")
    # A group made before owners existed, or from the CLI, has none. Leaving it open is
    # better than locking it to nobody.
    if group.owner_account_id is None:
        return
    if group.owner_account_id != account.id:
        raise ForbiddenError("Это может сделать только владелец группы")


async def require_organiser(session: AsyncSession, actor: Actor, tournament_id: uuid.UUID) -> None:
    """The organiser, or the group's owner if the organiser walked off with the phone."""
    if actor is System:
        return
    account = _identified(actor)
    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise TournamentNotFoundError(f"no tournament with id {tournament_id}")
    if tournament.organiser_account_id is None:
        return
    if tournament.organiser_account_id == account.id:
        return

    group = await session.get(Group, tournament.group_id)
    if group is not None and group.owner_account_id == account.id:
        return
    raise ForbiddenError("Это может сделать только тот, кто начал турнир")


async def require_can_score(
    session: AsyncSession,
    actor: Actor,
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
    account = _identified(actor)

    tournament = await session.get(Tournament, tournament_id)
    if tournament is None:
        raise TournamentNotFoundError(f"no tournament with id {tournament_id}")
    await require_member(session, account, tournament.group_id)
    if tournament.organiser_account_id is None or tournament.organiser_account_id == account.id:
        return

    plays_as = await session.scalar(
        select(Player.id)
        .join(TournamentPlayer, TournamentPlayer.player_id == Player.id)
        .where(TournamentPlayer.tournament_id == tournament_id, Player.account_id == account.id)
    )
    if plays_as is None:
        return
    if plays_as not in players_on_court:
        raise ForbiddenError("Счёт вносит тот, кто играл этот матч, или организатор")
