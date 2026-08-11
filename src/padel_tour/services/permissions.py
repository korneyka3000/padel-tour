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

from padel_tour import repositories
from padel_tour.db import PROVIDER_TELEGRAM
from padel_tour.settings import settings

from .errors import (
    ForbiddenError,
    GroupNotFoundError,
    NotAMemberError,
    NotOnThisCourtError,
    NotSignedInError,
    NotTheOrganiserError,
    NotTheOwnerError,
    TournamentNotFoundError,
)
from .views import Viewing

if TYPE_CHECKING:
    import uuid

    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account

    from .views import TournamentView


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
        raise NotSignedInError("sign in to see this")
    return actor


async def is_admin(session: AsyncSession, actor: Account) -> bool:
    """Is this account allowed everywhere?

    Read from configuration rather than stored on the row on purpose: the list of people
    who can reach into any group belongs with the deployment, not in data that a bug — or
    somebody with a database client — could quietly change.
    """
    allowed = settings().admins
    if not allowed:
        return False
    identities = await repositories.external_ids_of(session, actor.id, PROVIDER_TELEGRAM)
    return any(external in allowed for external in identities)


async def is_member(session: AsyncSession, actor: Account, group_id: uuid.UUID) -> bool:
    """Does this account play in this group?"""
    player = await repositories.player_of_account(session, group_id, actor.id)
    if player is not None:
        return True
    # An owner who has not claimed a player of their own still belongs here.
    group = await repositories.group_by_id(session, group_id)
    return group is not None and group.owner_account_id == actor.id


async def require_member(session: AsyncSession, actor: Actor, group_id: uuid.UUID) -> None:
    if actor is System:
        return
    account = _identified(actor)
    group = await repositories.group_by_id(session, group_id)
    if group is None:
        raise GroupNotFoundError(f"no group with id {group_id}")
    # A group nobody owns — made from the CLI, or before owners existed — is open. Locking
    # it to nobody would strand the people already in it.
    if group.owner_account_id is None:
        return
    if not await is_member(session, account, group_id) and not await is_admin(session, account):
        raise NotAMemberError("you are not a member of this group")


async def require_owner(session: AsyncSession, actor: Actor, group_id: uuid.UUID) -> None:
    if actor is System:
        return
    account = _identified(actor)
    group = await repositories.group_by_id(session, group_id)
    if group is None:
        raise GroupNotFoundError(f"no group with id {group_id}")
    # A group made before owners existed, or from the CLI, has none. Leaving it open is
    # better than locking it to nobody.
    if group.owner_account_id is None:
        return
    if group.owner_account_id != account.id and not await is_admin(session, account):
        raise NotTheOwnerError("only the group owner can do this")


async def require_organiser(session: AsyncSession, actor: Actor, tournament_id: uuid.UUID) -> None:
    """The organiser, or the group's owner if the organiser walked off with the phone."""
    if actor is System:
        return
    account = _identified(actor)
    tournament = await repositories.tournament_row(session, tournament_id)
    if tournament is None:
        raise TournamentNotFoundError(f"no tournament with id {tournament_id}")
    if tournament.organiser_account_id is None:
        return
    if tournament.organiser_account_id == account.id:
        return

    group = await repositories.group_by_id(session, tournament.group_id)
    if group is not None and group.owner_account_id == account.id:
        return
    if await is_admin(session, account):
        return
    raise NotTheOrganiserError("only whoever started this tournament can do this")


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

    tournament = await repositories.tournament_row(session, tournament_id)
    if tournament is None:
        raise TournamentNotFoundError(f"no tournament with id {tournament_id}")
    await require_member(session, account, tournament.group_id)
    if tournament.organiser_account_id is None or tournament.organiser_account_id == account.id:
        return

    plays_as = await _plays_as(session, account, tournament_id)
    if plays_as is None:
        return
    if plays_as not in players_on_court:
        raise NotOnThisCourtError(
            "scores are entered by whoever played the match, or the organiser"
        )


async def _plays_as(
    session: AsyncSession, account: Account, tournament_id: uuid.UUID
) -> uuid.UUID | None:
    """The player this account holds in this tournament, if they have claimed one."""
    return await repositories.player_id_in_tournament(session, tournament_id, account.id)


# --------------------------------------------------------------------------- asking instead


async def can_see(session: AsyncSession, actor: Actor, group_id: uuid.UUID) -> bool:
    """:func:`require_member` asked as a question.

    Written as a call rather than a copy of the condition on purpose. An interface that has
    to grey out a control needs the same answer the service layer will give, and two
    implementations of one rule drift the first time the rule changes.
    """
    try:
        await require_member(session, actor, group_id)
    except ForbiddenError, NotSignedInError:
        return False
    return True


async def can_organise(session: AsyncSession, actor: Actor, tournament_id: uuid.UUID) -> bool:
    """:func:`require_organiser` asked as a question."""
    try:
        await require_organiser(session, actor, tournament_id)
    except ForbiddenError, NotSignedInError:
        return False
    return True


async def viewing(session: AsyncSession, actor: Actor, tournament: TournamentView) -> Viewing:
    """What this caller is, relative to this tournament.

    The inputs to :func:`require_can_score` rather than its verdict. A screen showing four
    courts needs to know which of them it may offer to score, and the honest way to tell it
    is to hand over what the rule reads — not a boolean per match, which would be one field
    per court, all of them stale the moment a Mexicano draws its next round.
    """
    if not await can_see(session, actor, tournament.group_id):
        return Viewing()

    account = None if actor is None or isinstance(actor, Anonymous) else actor
    return Viewing(
        is_member=True,
        is_organiser=await can_organise(session, actor, tournament.id),
        plays_as=None if account is None else await _plays_as(session, account, tournament.id),
        anyone_may_score=tournament.organiser_account_id is None,
    )
