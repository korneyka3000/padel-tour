"""Leaderboard and per-round progression.

Both formats score the same way: a match played to N points hands each player their own
team's score. 14:10 means +14 to both winners and +10 to both losers.

The tie-break cascade is deliberately total — it can never leave two players unordered.
That is not cosmetic: in a Mexicano the standing *is* the draw for the next round, so an
ambiguous order would make the tournament non-reproducible.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from itertools import groupby

from .models import Match, PlayerId, ProgressPoint, StandingRow, TournamentState


@dataclass(slots=True)
class _Tally:
    played: int = 0
    wins: int = 0
    draws: int = 0
    losses: int = 0
    points_for: int = 0
    points_against: int = 0

    @property
    def diff(self) -> int:
        return self.points_for - self.points_against


def _record_match(
    match: Match,
    tallies: dict[PlayerId, _Tally],
    head_to_head: dict[tuple[PlayerId, PlayerId], int],
) -> None:
    """Fold one played match into the running tallies."""
    if match.result is None:
        return
    score_a, score_b = match.result.score_a, match.result.score_b

    for team, scored, conceded in (
        (match.team_a, score_a, score_b),
        (match.team_b, score_b, score_a),
    ):
        for player in team:
            tally = tallies[player]
            tally.played += 1
            tally.points_for += scored
            tally.points_against += conceded
            if scored > conceded:
                tally.wins += 1
            elif scored == conceded:
                tally.draws += 1
            else:
                tally.losses += 1

    for left in match.team_a:
        for right in match.team_b:
            head_to_head[(left, right)] += score_a
            head_to_head[(right, left)] += score_b


def _collect(
    state: TournamentState, through_round: int | None
) -> tuple[dict[PlayerId, _Tally], dict[tuple[PlayerId, PlayerId], int]]:
    """Accumulate per-player tallies and head-to-head points scored."""
    tallies: dict[PlayerId, _Tally] = {player: _Tally() for player in state.players}
    head_to_head: dict[tuple[PlayerId, PlayerId], int] = defaultdict(int)

    for rnd in state.rounds:
        if through_round is not None and rnd.number > through_round:
            continue
        for match in rnd.matches:
            _record_match(match, tallies, head_to_head)

    return tallies, head_to_head


def standings(
    state: TournamentState, *, through_round: int | None = None
) -> tuple[StandingRow, ...]:
    """The leaderboard, best first, with ranks 1..n and no shared places.

    Tie-breaks, in order: points scored, wins, head-to-head, draw order.

    Head-to-head is a mini-league among the players still tied on points and wins: each is
    scored on the points they took off the *others in that group*. Draw order — the roster
    shuffled once at creation from the tournament seed — is the guaranteed last word.

    Point difference is deliberately *not* a tie-break. Every match is played to a fixed
    total, so ``difference = 2 × scored − target × played``: among players who have played
    the same number of matches, equal points always means equal difference. It is kept on
    :class:`StandingRow` because it reads well in a table, not because it decides anything.
    """
    tallies, head_to_head = _collect(state, through_round)
    draw_index = {player: index for index, player in enumerate(state.draw_order)}

    def coarse_key(player: PlayerId) -> tuple[int, int]:
        tally = tallies[player]
        return (-tally.points_for, -tally.wins)

    ordered = sorted(state.players, key=lambda p: (*coarse_key(p), draw_index[p]))

    resolved: list[PlayerId] = []
    for _, tied in groupby(ordered, key=coarse_key):
        group = list(tied)
        if len(group) > 1:
            members = set(group)
            group.sort(
                key=lambda p: (
                    -sum(head_to_head[(p, other)] for other in members if other != p),
                    draw_index[p],
                )
            )
        resolved.extend(group)

    return tuple(
        StandingRow(
            rank=rank,
            player=player,
            played=tallies[player].played,
            wins=tallies[player].wins,
            draws=tallies[player].draws,
            losses=tallies[player].losses,
            points_for=tallies[player].points_for,
            points_against=tallies[player].points_against,
        )
        for rank, player in enumerate(resolved, start=1)
    )


def ranked_players(state: TournamentState, *, through_round: int | None = None) -> list[PlayerId]:
    """Just the player ids in standing order — what Mexicano needs to draw the next round."""
    return [row.player for row in standings(state, through_round=through_round)]


def progression(state: TournamentState) -> dict[PlayerId, tuple[ProgressPoint, ...]]:
    """Per-player series for the round-by-round chart.

    One point per round that has at least one result, so the series always agrees with the
    leaderboard. A player whose match in that round is still unfinished contributes zero for
    the round and their cumulative total stays flat.
    """
    series: dict[PlayerId, list[ProgressPoint]] = {player: [] for player in state.players}

    for rnd in state.rounds:
        round_points: dict[PlayerId, tuple[int, int]] = {}
        for match in rnd.matches:
            if match.result is None:
                continue
            score_a, score_b = match.result.score_a, match.result.score_b
            for player in match.team_a:
                round_points[player] = (score_a, score_b)
            for player in match.team_b:
                round_points[player] = (score_b, score_a)
        if not round_points:
            continue

        for row in standings(state, through_round=rnd.number):
            scored, conceded = round_points.get(row.player, (0, 0))
            series[row.player].append(
                ProgressPoint(
                    round_no=rnd.number,
                    points_for=scored,
                    points_against=conceded,
                    cumulative_points=row.points_for,
                    rank=row.rank,
                )
            )

    return {player: tuple(points) for player, points in series.items()}
