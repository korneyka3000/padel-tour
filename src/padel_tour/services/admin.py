"""What an administrator can see and do that an ordinary member cannot.

Everything here is still the service layer: the rules are the same ones the bot and the web
obey, and an admin is somebody the permission checks do not stop. What is different is the
*scope* of the questions — across every group rather than inside one — and a handful of
operations nobody else has any business asking for.

Two of those operations delete things. Both answer, first, what would go with them: the
foreign keys cascade, so removing a group takes its roster and every tournament it ever
played, and a confirmation that does not say so is asking for a yes to a question nobody was
shown.

Deleting a **player** is deliberately not here. Players are deactivated, never removed —
somebody who leaves still has to appear in the tournaments they played, or the history stops
adding up (``db/models.py``).
"""

from __future__ import annotations

import logging
import uuid  # noqa: TC003 - Pydantic resolves annotations when the class is built
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from padel_tour import repositories
from padel_tour.db import PROVIDER_EMAIL, PROVIDER_TELEGRAM

from .errors import (
    ForbiddenError,
    GroupNotFoundError,
    PlayerNotFoundError,
    TournamentNotFoundError,
)
from .invites import claim_player, release_player
from .views import TournamentSummary, View

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


logger = logging.getLogger(__name__)


class Identified(View):
    """One way somebody signs in: which provider, and who they are there."""

    provider: str
    external_id: str


class Held(View):
    """A player this account holds: enough to name them, and enough to let them go."""

    id: uuid.UUID
    name: str


class AccountView(View):
    """An account as an administrator needs to see it.

    Carries the ways in, because "who is this" is unanswerable without them: an account has
    a display name only if some integration happened to supply one, and most have none.
    """

    id: uuid.UUID
    display_name: str | None
    created_at: datetime
    identities: tuple[Identified, ...] = ()
    #: The players this account holds. Ids as well as names, because the screen that lists
    #: these is also the one that detaches them, and a name is not something to act on.
    players: tuple[Held, ...] = ()
    #: Last time a live session was used. Absent once they sign out everywhere — the honest
    #: answer, since signing out is what deletes the evidence.
    last_seen: datetime | None = None

    #: Whether the configuration lists this account, by either door.
    is_admin: bool = False


class Totals(View):
    """The size of the whole thing, for the one screen that asks."""

    accounts: int
    groups: int
    players: int
    tournaments: int


class Doomed(View):
    """What a delete would take with it. Answered before the delete, never after."""

    name: str
    players: int = 0
    tournaments: int = 0


async def totals(session: AsyncSession) -> Totals:
    return Totals(
        accounts=await repositories.count_accounts(session),
        groups=await repositories.count_groups(session),
        players=await repositories.count_players(session),
        tournaments=await repositories.count_all_tournaments(session),
    )


async def list_accounts(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[AccountView]:
    """Every account, newest first, with the ways in and when they were last here.

    Three queries whatever the page size — accounts, then identities and last-seen in bulk.
    Reading either through a relationship per row is the N+1 the repository layer exists to
    prevent, and an admin list is exactly where it would first be felt.
    """
    from .permissions import is_admin  # noqa: PLC0415 - permissions imports views, not this

    rows = await repositories.all_accounts(session, limit=limit, offset=offset)
    ids = [row.id for row in rows]
    identities = await repositories.identities_of(session, ids)
    seen = await repositories.last_seen_of(session, ids)
    held = await repositories.players_of_accounts(session, ids)

    found: list[AccountView] = []
    for row in rows:
        found_view = AccountView(
            id=row.id,
            display_name=row.display_name,
            created_at=row.created_at,
            identities=tuple(
                Identified(provider=provider, external_id=external)
                for provider, external in identities.get(row.id, ())
            ),
            players=tuple(
                Held(id=player_id, name=name) for player_id, name in held.get(row.id, ())
            ),
            last_seen=seen.get(row.id),
            is_admin=await is_admin(session, row),
        )
        found.append(found_view)
    return found


async def attach_player(session: AsyncSession, player_id: uuid.UUID, account_id: uuid.UUID) -> None:
    """Bind a player to somebody else's account.

    The ordinary claim already takes whichever account it is told to; what an admin needs is
    a route to it that is not "be that person". The guards stay — a player already spoken for
    cannot be taken, and nobody plays as two people in one group — because those are what
    stop a slip from attaching one person's history to another.
    """
    account = await repositories.account_by_id(session, account_id)
    if account is None:
        raise ForbiddenError("no such account")
    await claim_player(session, player_id, account)
    logger.warning("admin attached player %s to account %s", player_id, account_id)


async def detach_player(session: AsyncSession, player_id: uuid.UUID) -> None:
    """Let go of a player on behalf of whoever holds them."""
    player = await repositories.player_by_id(session, player_id)
    if player is None:
        raise PlayerNotFoundError("that player no longer exists")
    if player.account_id is None:
        return
    holder = await repositories.account_by_id(session, player.account_id)
    if holder is None:  # pragma: no cover - the foreign key cascades
        raise PlayerNotFoundError("that player no longer exists")
    await release_player(session, player_id, holder)
    logger.warning("admin detached player %s from account %s", player_id, holder.id)


async def group_impact(session: AsyncSession, group_id: uuid.UUID) -> Doomed:
    """What deleting this group would destroy."""
    group = await repositories.group_by_id(session, group_id)
    if group is None:
        raise GroupNotFoundError(f"no group with id {group_id}")
    players, tournaments = await repositories.counts_under(session, group_id)
    return Doomed(name=group.name, players=players, tournaments=tournaments)


async def delete_group(session: AsyncSession, group_id: uuid.UUID) -> Doomed:
    """Delete a group and everything under it. Answers what it took."""
    doomed = await group_impact(session, group_id)
    group = await repositories.group_by_id(session, group_id)
    if group is None:  # pragma: no cover - checked a line ago
        raise GroupNotFoundError(f"no group with id {group_id}")
    await repositories.drop_group(session, group)
    logger.warning(
        "admin deleted group %s (%s) with %d players and %d tournaments",
        group_id,
        doomed.name,
        doomed.players,
        doomed.tournaments,
    )
    return doomed


async def delete_tournament(session: AsyncSession, tournament_id: uuid.UUID) -> None:
    """Delete one tournament with its rounds and results. The group is left alone."""
    row = await repositories.tournament_row(session, tournament_id)
    if row is None:
        raise TournamentNotFoundError(f"no tournament with id {tournament_id}")
    await repositories.drop_tournament(session, row)
    logger.warning("admin deleted tournament %s", tournament_id)


async def set_owner(
    session: AsyncSession, group_id: uuid.UUID, account_id: uuid.UUID | None
) -> None:
    """Hand a group to somebody, or to nobody.

    ``None`` is a real choice, not a clearing: a group with no owner is the shape a chat
    makes, and the service layer reads it as "open to whoever is in it" rather than as
    "locked". Handing one back to nobody is how a group stuck behind a departed owner gets
    unstuck.
    """
    group = await repositories.group_by_id(session, group_id)
    if group is None:
        raise GroupNotFoundError(f"no group with id {group_id}")
    if account_id is not None and await repositories.account_by_id(session, account_id) is None:
        raise ForbiddenError("no such account")
    group.owner_account_id = account_id
    await session.flush()
    logger.warning("admin set owner of group %s to %s", group_id, account_id)


#: The providers an identity can carry, for a screen that has to name them.
PROVIDERS = (PROVIDER_TELEGRAM, PROVIDER_EMAIL)


async def all_tournaments(
    session: AsyncSession, *, limit: int = 50, offset: int = 0
) -> list[TournamentSummary]:
    """Every tournament there is, newest first, with the group named on each line.

    The same summary the group archive and "my tournaments" use, so an admin reading the
    list sees exactly what the people in it see, plus which group it belongs to.
    """
    from .tournaments import _to_summary  # noqa: PLC0415 - tournaments imports views, not this

    rows = await repositories.all_tournaments(session, limit=limit, offset=offset)
    names = await repositories.group_names(session, {row.group_id for row in rows})
    return [_to_summary(row, group_name=names.get(row.group_id)) for row in rows]
