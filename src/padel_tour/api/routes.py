"""Read endpoints, shaped by the screens that consume them.

Nothing here writes. The bot and the CLI still do that; a public write endpoint with no
authentication would be a hole, and accounts do not arrive until M5.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Response, status
from sqlalchemy import text

from padel_tour.services import (
    active_tournament,
    get_tournament,
    list_groups,
    list_players,
    list_tournaments,
)
from padel_tour.services.groups import get_group
from padel_tour.services.stats import player_stats

from .deps import Session
from .schemas import (
    Group,
    GroupDetail,
    Health,
    Player,
    PlayerProfile,
    Tournament,
    TournamentCard,
)

#: Everything the API serves lives under this prefix. In production it is also what tells
#: the deployment to route a request to the function rather than to the web app.
API_PREFIX = "/api"

router = APIRouter(prefix=API_PREFIX)

#: Archive page size. Enough that a group's whole season usually fits in one request.
DEFAULT_PAGE = 20
MAX_PAGE = 100


@router.get("/health", response_model=Health, tags=["meta"])
async def health(session: Session) -> Health:
    """Is the service up, and can it reach the database?

    The query matters: a process that starts but cannot see Postgres is not healthy, and
    reporting otherwise turns a clear failure into a mystery.
    """
    try:
        await session.execute(text("SELECT 1"))
    except Exception:  # any failure here means the same thing to a caller
        return Health(status="degraded", database="unreachable")
    return Health(status="ok", database="ok")


@router.get("/groups", response_model=list[Group], tags=["groups"])
async def read_groups(session: Session) -> list[Group]:
    return [Group.of(view) for view in await list_groups(session)]


@router.get("/groups/{group_id}", response_model=GroupDetail, tags=["groups"])
async def read_group(group_id: uuid.UUID, session: Session) -> GroupDetail:
    group = await get_group(session, group_id)
    roster = await list_players(session, group_id)
    return GroupDetail(
        id=group.id,
        name=group.name,
        players=[Player.of(player) for player in roster],
    )


@router.get(
    "/groups/{group_id}/tournaments",
    response_model=list[TournamentCard],
    tags=["groups"],
)
async def read_archive(
    group_id: uuid.UUID,
    session: Session,
    limit: int = Query(DEFAULT_PAGE, ge=1, le=MAX_PAGE),
    offset: int = Query(0, ge=0),
) -> list[TournamentCard]:
    summaries = await list_tournaments(session, group_id, limit=limit, offset=offset)
    return [TournamentCard.of(summary) for summary in summaries]


@router.get(
    "/groups/{group_id}/active",
    response_model=Tournament,
    responses={204: {"description": "Nothing is being played right now"}},
    tags=["groups"],
)
async def read_active(group_id: uuid.UUID, session: Session) -> Tournament | Response:
    """The tournament in progress.

    An empty court is not an error, so this answers 204 rather than 404 — the group exists,
    it simply is not playing.
    """
    await get_group(session, group_id)
    view = await active_tournament(session, group_id)
    if view is None:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    return Tournament.of(view)


@router.get("/tournaments/{tournament_id}", response_model=Tournament, tags=["tournaments"])
async def read_tournament(tournament_id: uuid.UUID, session: Session) -> Tournament:
    return Tournament.of(await get_tournament(session, tournament_id))


@router.get("/players/{player_id}", response_model=PlayerProfile, tags=["players"])
async def read_player(player_id: uuid.UUID, session: Session) -> PlayerProfile:
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
        history=[TournamentCard.of(entry) for entry in stats.history],
    )


__all__ = ["router"]
