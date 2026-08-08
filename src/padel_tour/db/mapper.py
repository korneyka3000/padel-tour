"""Translation between stored rows and the engine's :class:`TournamentState`.

The engine treats players as opaque string ids, so we hand it stringified UUIDs. Names are
attached only at the very edge, when building something for a human to look at. That is why
renaming a player touches no tournament: no tournament ever stored their name.

Saving is incremental. Recording a score is one UPDATE of one match row, not a rewrite of
the tournament, so two people entering results on different courts do not clobber each
other's work.
"""

from __future__ import annotations

import uuid

from padel_tour.engine import (
    Format,
    Match,
    MatchResult,
    PairingPattern,
    PlayerId,
    Round,
    Team,
    TournamentConfig,
    TournamentState,
)

from .models import Match as MatchRow
from .models import Round as RoundRow
from .models import Tournament as TournamentRow
from .models import TournamentStatus, utc_now


def to_player_id(value: uuid.UUID) -> PlayerId:
    """The engine's view of a player: their id as a plain string."""
    return str(value)


def to_uuid(value: PlayerId) -> uuid.UUID:
    return uuid.UUID(value)


def load_state(row: TournamentRow) -> TournamentState:
    """Rebuild the engine state from a tournament and its loaded relations.

    Expects ``entries``, ``rounds`` and each round's ``matches`` to be eagerly loaded; the
    repository is responsible for that.
    """
    fmt = Format(row.format)
    config = TournamentConfig(
        format=fmt,
        points_per_match=row.points_per_match,
        pairing_pattern=PairingPattern(row.pairing_pattern),
        rounds=row.total_rounds if fmt is Format.MEXICANO else None,
    )

    ordered_entries = sorted(row.entries, key=lambda entry: entry.draw_position)
    draw_order = tuple(to_player_id(entry.player_id) for entry in ordered_entries)

    rounds = tuple(
        Round(
            number=round_row.number,
            matches=tuple(
                _load_match(match_row)
                for match_row in sorted(round_row.matches, key=lambda m: m.court)
            ),
        )
        for round_row in sorted(row.rounds, key=lambda r: r.number)
    )

    return TournamentState(
        config=config,
        # Registration order is not stored separately: the draw is the only order the engine
        # needs, and every roster operation it performs is order-independent.
        players=draw_order,
        draw_order=draw_order,
        seed=row.seed,
        total_rounds=row.total_rounds,
        rounds=rounds,
        finished=row.status == TournamentStatus.FINISHED,
    )


def _load_match(row: MatchRow) -> Match:
    result = (
        MatchResult(row.score_a, row.score_b)
        if row.score_a is not None and row.score_b is not None
        else None
    )
    return Match(
        court=row.court,
        team_a=Team(to_player_id(row.team_a1), to_player_id(row.team_a2)),
        team_b=Team(to_player_id(row.team_b1), to_player_id(row.team_b2)),
        result=result,
    )


def build_match_row(match: Match) -> MatchRow:
    """A detached match row, ready to be appended to a round's ``matches``.

    The foreign key is filled in by the relationship on flush rather than set here — primary
    keys do not exist until then.
    """
    return MatchRow(
        court=match.court,
        team_a1=to_uuid(match.team_a.a),
        team_a2=to_uuid(match.team_a.b),
        team_b1=to_uuid(match.team_b.a),
        team_b2=to_uuid(match.team_b.b),
        score_a=match.result.score_a if match.result else None,
        score_b=match.result.score_b if match.result else None,
    )


def build_round_row(rnd: Round) -> RoundRow:
    """A detached round row with its matches, ready to append to a tournament."""
    row = RoundRow(number=rnd.number)
    row.matches = [build_match_row(match) for match in rnd.matches]
    return row


def sync_state(row: TournamentRow, state: TournamentState) -> None:
    """Write back whatever the engine changed, and nothing else.

    Three kinds of change can happen: a score appears or is corrected, a Mexicano draws a
    new round, and the tournament finishes. Everything else about a tournament is fixed at
    creation, so there is nothing else to look at.
    """
    rows_by_number = {round_row.number: round_row for round_row in row.rounds}

    for rnd in state.rounds:
        round_row = rows_by_number.get(rnd.number)
        if round_row is None:
            row.rounds.append(build_round_row(rnd))
            continue
        _sync_round(round_row, rnd)

    was_finished = row.status == TournamentStatus.FINISHED
    if state.finished and not was_finished:
        row.status = TournamentStatus.FINISHED
        row.finished_at = utc_now()
    elif not state.finished and was_finished:
        row.status = TournamentStatus.ACTIVE
        row.finished_at = None


def _sync_round(round_row: RoundRow, rnd: Round) -> None:
    match_rows = {match_row.court: match_row for match_row in round_row.matches}
    for match in rnd.matches:
        match_row = match_rows.get(match.court)
        if match_row is None:
            round_row.matches.append(build_match_row(match))
            continue
        score_a = match.result.score_a if match.result else None
        score_b = match.result.score_b if match.result else None
        if (match_row.score_a, match_row.score_b) != (score_a, score_b):
            match_row.score_a = score_a
            match_row.score_b = score_b
