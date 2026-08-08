"""The life of a tournament, from draw to final table.

Every function loads the stored tournament, rebuilds the engine state, asks the engine to do
the work, and writes back only what changed. The rules live in the engine and nowhere else;
what lives here is everything the engine cannot know — who these players are, which group
they belong to, and whether this is allowed right now.

None of these functions commit. The caller owns the transaction.
"""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from padel_tour.db import Player, Round, Tournament, TournamentPlayer, TournamentStatus
from padel_tour.db.mapper import build_round_row, load_state, sync_state, to_uuid
from padel_tour.engine import (
    Format,
    TournamentConfig,
    TournamentState,
    amend_result,
    create_americano,
    create_mexicano,
    finish,
    next_round,
    progression,
    record_result,
    reroll,
    standings,
)

from .errors import (
    ActiveTournamentExistsError,
    InactivePlayerError,
    PlayerNotInGroupError,
    TournamentNotFoundError,
)
from .groups import get_group
from .views import (
    MatchView,
    RoundView,
    StandingView,
    TournamentSummary,
    TournamentView,
)

if TYPE_CHECKING:
    import uuid
    from collections.abc import Sequence

    from sqlalchemy.ext.asyncio import AsyncSession
    from sqlalchemy.sql.base import ExecutableOption

_SEED_BITS = 32


def _loaded() -> tuple[ExecutableOption, ...]:
    """Eager-load options for a tournament the mapper can rebuild from."""
    return (
        selectinload(Tournament.entries).selectinload(TournamentPlayer.player),
        selectinload(Tournament.rounds).selectinload(Round.matches),
    )


async def _load(session: AsyncSession, tournament_id: uuid.UUID) -> Tournament:
    row = await session.scalar(
        select(Tournament).where(Tournament.id == tournament_id).options(*_loaded())
    )
    if row is None:
        raise TournamentNotFoundError(f"no tournament with id {tournament_id}")
    return row


def _names(row: Tournament) -> dict[str, str]:
    """Player id (as the engine sees it) to display name."""
    return {str(entry.player_id): entry.player.name for entry in row.entries}


def _to_view(row: Tournament, state: TournamentState) -> TournamentView:
    names = _names(row)

    rounds = tuple(
        RoundView(
            number=rnd.number,
            matches=tuple(
                MatchView(
                    court=match.court,
                    team_a=(names[match.team_a.a], names[match.team_a.b]),
                    team_b=(names[match.team_b.a], names[match.team_b.b]),
                    score_a=match.result.score_a if match.result else None,
                    score_b=match.result.score_b if match.result else None,
                )
                for match in rnd.matches
            ),
        )
        for rnd in state.rounds
    )

    table = tuple(
        StandingView(
            rank=line.rank,
            player_id=to_uuid(line.player),
            name=names[line.player],
            played=line.played,
            wins=line.wins,
            draws=line.draws,
            losses=line.losses,
            points_for=line.points_for,
            points_against=line.points_against,
        )
        for line in standings(state)
    )

    return TournamentView(
        id=row.id,
        group_id=row.group_id,
        format=Format(row.format),
        points_per_match=row.points_per_match,
        pairing_pattern=state.config.pairing_pattern,
        total_rounds=row.total_rounds,
        finished=state.finished,
        created_at=row.created_at,
        finished_at=row.finished_at,
        rounds=rounds,
        standings=table,
        progression={to_uuid(player): points for player, points in progression(state).items()},
        state=state,
    )


def _entries_for(state: TournamentState) -> list[TournamentPlayer]:
    """Roster rows carrying the draw order the engine settled on."""
    return [
        TournamentPlayer(player_id=to_uuid(player_id), draw_position=position)
        for position, player_id in enumerate(state.draw_order)
    ]


def _to_summary(row: Tournament) -> TournamentSummary:
    """An archive line. Naming the winner means ranking, so the engine runs here too."""
    state = load_state(row)
    table = standings(state)
    played = sum(1 for rnd in state.rounds if rnd.complete)
    return TournamentSummary(
        id=row.id,
        group_id=row.group_id,
        format=Format(row.format),
        finished=state.finished,
        player_count=len(row.entries),
        rounds_played=played,
        total_rounds=row.total_rounds,
        created_at=row.created_at,
        finished_at=row.finished_at,
        winner_name=_names(row)[table[0].player] if table and played else None,
    )


async def _refreshed_view(session: AsyncSession, row: Tournament) -> TournamentView:
    """Flush pending changes, then build a view from what is now stored."""
    await session.flush()
    await session.refresh(row, ["rounds"])
    for round_row in row.rounds:
        await session.refresh(round_row, ["matches"])
    return _to_view(row, load_state(row))


async def _validate_roster(
    session: AsyncSession, group_id: uuid.UUID, player_ids: Sequence[uuid.UUID]
) -> list[Player]:
    """Every entered player must exist, be active, and belong to this group."""
    players = list(await session.scalars(select(Player).where(Player.id.in_(player_ids))))
    found = {player.id: player for player in players}

    missing = [pid for pid in player_ids if pid not in found]
    if missing:
        raise PlayerNotInGroupError(f"unknown players: {', '.join(str(pid) for pid in missing)}")

    outsiders = [p.name for p in players if p.group_id != group_id]
    if outsiders:
        raise PlayerNotInGroupError(f"not in this group: {', '.join(sorted(outsiders))}")

    retired = [p.name for p in players if not p.is_active]
    if retired:
        raise InactivePlayerError(f"no longer on the roster: {', '.join(sorted(retired))}")

    return [found[pid] for pid in player_ids]


async def active_tournament(session: AsyncSession, group_id: uuid.UUID) -> TournamentView | None:
    """The group's tournament in progress, if one is running."""
    row = await session.scalar(
        select(Tournament)
        .where(
            Tournament.group_id == group_id,
            Tournament.status == TournamentStatus.ACTIVE,
        )
        .order_by(Tournament.created_at.desc())
        .options(*_loaded())
    )
    return None if row is None else _to_view(row, load_state(row))


async def start_tournament(
    session: AsyncSession,
    group_id: uuid.UUID,
    player_ids: Sequence[uuid.UUID],
    config: TournamentConfig,
    *,
    seed: int | None = None,
) -> TournamentView:
    """Draw a new tournament for a group.

    Refuses if the group already has one running: the bot shows one screen per chat, and a
    second live tournament would make that screen ambiguous.
    """
    await get_group(session, group_id)

    if await active_tournament(session, group_id) is not None:
        raise ActiveTournamentExistsError(
            "this group already has a tournament in progress — finish it first"
        )

    players = await _validate_roster(session, group_id, player_ids)
    chosen_seed = seed if seed is not None else secrets.randbits(_SEED_BITS)

    engine_ids = [str(player.id) for player in players]
    state = (
        create_americano(engine_ids, config, chosen_seed)
        if config.format is Format.AMERICANO
        else create_mexicano(engine_ids, config, chosen_seed)
    )

    row = Tournament(
        group_id=group_id,
        format=config.format,
        points_per_match=config.points_per_match,
        pairing_pattern=config.pairing_pattern,
        total_rounds=state.total_rounds,
        seed=chosen_seed,
        status=TournamentStatus.ACTIVE,
    )
    row.entries = _entries_for(state)
    row.rounds = [build_round_row(rnd) for rnd in state.rounds]
    session.add(row)

    await session.flush()
    return await get_tournament(session, row.id)


async def reroll_tournament(
    session: AsyncSession, tournament_id: uuid.UUID, *, seed: int | None = None
) -> TournamentView:
    """Redraw before the first result. The engine refuses once play has started."""
    row = await _load(session, tournament_id)
    state = reroll(load_state(row), seed=seed)

    # A reroll replaces the draw wholesale — a new schedule and a new shuffle of the same
    # people — so rounds and entries are rebuilt rather than patched. Both are cleared and
    # flushed first: within one flush SQLAlchemy orders INSERTs before DELETEs, and since a
    # reshuffle is a permutation of values that are themselves unique, the new rows would
    # collide with the old ones still in the table.
    row.rounds.clear()
    row.entries.clear()
    await session.flush()

    row.entries.extend(_entries_for(state))
    row.rounds.extend(build_round_row(rnd) for rnd in state.rounds)
    row.seed = state.seed

    return await _refreshed_view(session, row)


async def record_score(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    *,
    round_no: int,
    court: int,
    score_a: int,
    score_b: int,
) -> TournamentView:
    """Score a match that has not been scored yet."""
    row = await _load(session, tournament_id)
    state = record_result(load_state(row), round_no, court, score_a, score_b)
    sync_state(row, state)
    return await _refreshed_view(session, row)


async def amend_score(
    session: AsyncSession,
    tournament_id: uuid.UUID,
    *,
    round_no: int,
    court: int,
    score_a: int,
    score_b: int,
) -> TournamentView:
    """Correct a score entered wrong. Standings and the chart recompute from it."""
    row = await _load(session, tournament_id)
    state = amend_result(load_state(row), round_no, court, score_a, score_b)
    sync_state(row, state)
    return await _refreshed_view(session, row)


async def advance_round(session: AsyncSession, tournament_id: uuid.UUID) -> TournamentView:
    """Draw the next Mexicano round from the current standing."""
    row = await _load(session, tournament_id)
    state = next_round(load_state(row))
    sync_state(row, state)
    return await _refreshed_view(session, row)


async def finish_tournament(session: AsyncSession, tournament_id: uuid.UUID) -> TournamentView:
    """End the tournament wherever it stands. Allowed at any round."""
    row = await _load(session, tournament_id)
    state = finish(load_state(row))
    sync_state(row, state)
    return await _refreshed_view(session, row)


async def get_tournament(session: AsyncSession, tournament_id: uuid.UUID) -> TournamentView:
    """Read a tournament back in full."""
    row = await _load(session, tournament_id)
    return _to_view(row, load_state(row))


async def list_tournaments(
    session: AsyncSession, group_id: uuid.UUID, *, limit: int = 20, offset: int = 0
) -> list[TournamentSummary]:
    """A group's tournaments, newest first.

    Summaries are built from the same loaded rows as a full view, because naming the winner
    means ranking the players, and ranking means running the engine's tie-break cascade.
    Cheap at group scale, and it guarantees the archive agrees with the detail page.
    """
    await get_group(session, group_id)
    rows = await session.scalars(
        select(Tournament)
        .where(Tournament.group_id == group_id)
        .order_by(Tournament.created_at.desc())
        .limit(limit)
        .offset(offset)
        .options(*_loaded())
    )

    return [_to_summary(row) for row in rows]


async def player_history(session: AsyncSession, player_id: uuid.UUID) -> list[TournamentSummary]:
    """Every tournament a player took part in, newest first."""
    rows = await session.scalars(
        select(Tournament)
        .join(TournamentPlayer, TournamentPlayer.tournament_id == Tournament.id)
        .where(TournamentPlayer.player_id == player_id)
        .order_by(Tournament.created_at.desc())
        .options(*_loaded())
    )
    return [_to_summary(row) for row in rows]


async def count_tournaments(session: AsyncSession, group_id: uuid.UUID) -> int:
    """How many tournaments a group has run. For paging the archive."""
    total = await session.scalar(
        select(func.count(Tournament.id)).where(Tournament.group_id == group_id)
    )
    return total or 0


__all__ = [
    "active_tournament",
    "advance_round",
    "amend_score",
    "count_tournaments",
    "finish_tournament",
    "get_tournament",
    "list_tournaments",
    "player_history",
    "record_score",
    "reroll_tournament",
    "start_tournament",
]
