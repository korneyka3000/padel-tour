"""Read endpoints, shaped by the screens that consume them.

Nothing here writes — writing lives in :mod:`padel_tour.api.auth` and
:mod:`padel_tour.api.invites`, and in the bot.

Visibility is not uniform. A group and its roster are private to its members; a tournament
is readable by anyone holding its link, because the point of a link is to show somebody the
table. Refusals are 403 rather than 404: an id is a UUIDv7 and cannot be guessed, so hiding
existence buys nothing, while "no access, ask for an invitation" is actionable and "broken
link" is not.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Response, status

# Aliased: `Tournament` in this module means the wire schema, and the two would
# otherwise shadow each other with the row losing.
from padel_tour import repositories
from padel_tour.db import Account, Base
from padel_tour.services import (
    active_tournament,
    get_tournament,
    groups_for_account,
    list_players,
    list_tournaments,
    require_member,
    viewing,
)
from padel_tour.services.groups import get_group, get_player
from padel_tour.services.permissions import Anonymous
from padel_tour.services.stats import player_stats

from .deps import API_PREFIX, CurrentAccount, Session
from .schemas import (
    Group,
    GroupDetail,
    Health,
    PlayerProfile,
    Tournament,
    TournamentCard,
)

router = APIRouter(prefix=API_PREFIX, tags=["read"])


def owns(owner_account_id: uuid.UUID | None, actor: Account | Anonymous) -> bool:
    """Whether the caller keeps this roster.

    A group nobody owns — one made from a Telegram chat — is everybody's, so anyone who can
    see it may also edit it. That matches what the service layer will actually allow, which
    is the point: a control that is shown must work.
    """
    if isinstance(actor, Anonymous):
        return False
    return owner_account_id in (None, actor.id)


#: Archive page size. Enough that a group's whole season usually fits in one request.
DEFAULT_PAGE = 20
MAX_PAGE = 100


@router.get("/health")
async def health(session: Session) -> Health:
    """Is the service up, can it reach the database, and does that database match this code?

    Connectivity was never the interesting question. Twice a deployment has landed before
    its migration and answered 500 to half the API while reporting itself perfectly healthy,
    because the code believed in a column the schema had not got (Р-039, Р-043).

    So it compares: one catalogue query for what the database has, the mapped metadata for
    what the code expects, and the answer names the difference.

    **Checked once per process, not once per request.** A catalogue scan is not free and
    uptime monitors call this every few seconds, while the schema can only move underneath a
    running process when somebody runs a migration — which on this deployment means a new
    process anyway. So a match is remembered and a mismatch is not: healthy stays cheap
    forever, and a process that saw a gap keeps looking until the migration lands and it
    can stop.
    """
    try:
        await repositories.ping(session)
    except Exception:  # any failure here means the same thing to a caller
        return Health(status="degraded", database="unreachable")

    missing = await _schema_gap(session)
    if missing is None:
        return Health(status="degraded", database="unreachable")
    if missing:
        # Named, because "degraded" sends somebody to the logs and this sends them to the
        # migration that has not run.
        return Health(status="degraded", database=f"schema behind code: {', '.join(missing)}")
    return Health(status="ok", database="ok")


#: Set once the schema has been seen to match, and never unset. See :func:`health`.
_schema_verified = False


async def _schema_gap(session: Session) -> list[str] | None:
    """Columns the code maps and the database has not got. ``None`` if we could not look."""
    global _schema_verified  # noqa: PLW0603 - one flag, one writer, and it only ever latches
    if _schema_verified:
        return []

    try:
        present = await repositories.present_columns(session)
    except Exception:
        return None

    missing = sorted(
        f"{table.name}.{column.name}"
        for table in Base.metadata.sorted_tables
        for column in table.columns
        if (table.name, column.name) not in present
    )
    if not missing:
        _schema_verified = True
    return missing


@router.get("/groups")
async def read_groups(session: Session, actor: CurrentAccount) -> list[Group]:
    """The groups you belong to. Signed out, that is none of them."""
    if isinstance(actor, Anonymous):
        return []
    return await groups_for_account(session, actor)


@router.get("/groups/{group_id}")
async def read_group(group_id: uuid.UUID, session: Session, actor: CurrentAccount) -> GroupDetail:
    group = await get_group(session, group_id)
    await require_member(session, actor, group_id)
    roster = await list_players(session, group_id)
    return GroupDetail(
        id=group.id,
        name=group.name,
        players=list(roster),
        is_owner=owns(group.owner_account_id, actor),
    )


@router.get("/groups/{group_id}/tournaments")
async def read_archive(
    group_id: uuid.UUID,
    session: Session,
    actor: CurrentAccount,
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE)] = DEFAULT_PAGE,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> list[TournamentCard]:
    await get_group(session, group_id)
    await require_member(session, actor, group_id)
    return await list_tournaments(session, group_id, limit=limit, offset=offset)


@router.get(
    "/groups/{group_id}/active",
    response_model=Tournament,
    responses={204: {"description": "Nothing is being played right now"}},
)
async def read_active(
    group_id: uuid.UUID, session: Session, actor: CurrentAccount
) -> Tournament | Response:
    """The tournament in progress.

    An empty court is not an error, so this answers 204 rather than 404 — the group exists,
    it simply is not playing.
    """
    await get_group(session, group_id)
    await require_member(session, actor, group_id)
    view = await active_tournament(session, group_id)
    if view is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return view.seen_by(await viewing(session, actor, view))


@router.get("/tournaments/{tournament_id}")
async def read_tournament(
    tournament_id: uuid.UUID, session: Session, actor: CurrentAccount
) -> Tournament:
    """Open to anyone holding the link — the whole point of a link is to show it to someone.

    Still asks who is looking. A stranger gets a page with no controls; the four who played
    court 2 get a score box on court 2. The account decides what is offered, never what is
    shown.
    """
    view = await get_tournament(session, tournament_id)
    return view.seen_by(await viewing(session, actor, view))


@router.get("/players/{player_id}")
async def read_player(
    player_id: uuid.UUID, session: Session, actor: CurrentAccount
) -> PlayerProfile:
    player = await get_player(session, player_id)
    await require_member(session, actor, player.group_id)
    stats = await player_stats(session, player_id)
    return PlayerProfile(
        id=stats.player_id,
        name=stats.name,
        tournaments=stats.tournaments,
        matches=stats.matches,
        wins=stats.wins,
        points_for=stats.points_for,
        average_points=stats.average_points,
        best_rank=stats.best_rank,
        podiums=stats.podiums,
        history=stats.history,
    )


__all__ = ["API_PREFIX", "router"]
