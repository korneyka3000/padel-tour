"""Leaderboard and tie-breaks.

The states here are hand-built rather than played out, because each tie-break stage needs a
very specific score pattern to be the deciding one.
"""

from __future__ import annotations

from random import Random

from conftest import americano, play_round, roster

from padel_tour.engine import (
    Format,
    Match,
    MatchResult,
    PlayerId,
    Round,
    Team,
    TournamentConfig,
    TournamentState,
    progression,
    standings,
)

Spec = tuple[tuple[str, str], tuple[str, str], int, int]


def build(
    players: tuple[PlayerId, ...],
    rounds_spec: list[list[Spec]],
    *,
    points: int = 24,
    draw_order: tuple[PlayerId, ...] | None = None,
) -> TournamentState:
    """A tournament state with exactly the matches and scores given."""
    rounds = tuple(
        Round(
            number=number,
            matches=tuple(
                Match(
                    court=court,
                    team_a=Team(*team_a),
                    team_b=Team(*team_b),
                    result=MatchResult(score_a, score_b),
                )
                for court, (team_a, team_b, score_a, score_b) in enumerate(spec, start=1)
            ),
        )
        for number, spec in enumerate(rounds_spec, start=1)
    )
    return TournamentState(
        config=TournamentConfig(Format.AMERICANO, points_per_match=points),
        players=players,
        draw_order=draw_order or players,
        seed=0,
        total_rounds=len(rounds_spec),
        rounds=rounds,
    )


def order_of(state: TournamentState) -> list[PlayerId]:
    return [row.player for row in standings(state)]


def test_each_player_banks_their_own_team_score() -> None:
    state = build(("A", "B", "C", "D"), [[(("A", "B"), ("C", "D"), 14, 10)]])
    rows = {row.player: row for row in standings(state)}
    assert (rows["A"].points_for, rows["A"].points_against) == (14, 10)
    assert (rows["B"].points_for, rows["B"].points_against) == (14, 10)
    assert (rows["C"].points_for, rows["C"].points_against) == (10, 14)
    assert rows["A"].wins == 1
    assert rows["C"].losses == 1


def test_a_draw_counts_as_a_draw() -> None:
    state = build(("A", "B", "C", "D"), [[(("A", "B"), ("C", "D"), 12, 12)]])
    rows = {row.player: row for row in standings(state)}
    assert all(rows[p].draws == 1 and rows[p].wins == 0 for p in ("A", "B", "C", "D"))


def test_ranks_are_dense_and_unique() -> None:
    state = play_round(americano(12), 1, Random(3))
    assert [row.rank for row in standings(state)] == list(range(1, 13))


def test_points_decide_first() -> None:
    state = build(("A", "B", "C", "D"), [[(("A", "B"), ("C", "D"), 20, 4)]])
    assert order_of(state)[:2] == ["A", "B"]


def test_wins_break_a_points_tie() -> None:
    """X and Y both hold 24 points; X won a match and Y only drew."""
    players = roster(8)
    x, y = "P01", "P02"
    state = build(
        players,
        [
            [
                ((x, "P03"), ("P04", "P05"), 24, 0),
                ((y, "P06"), ("P07", "P08"), 12, 12),
            ],
            [
                ((x, "P04"), ("P03", "P05"), 0, 24),
                ((y, "P07"), ("P06", "P08"), 12, 12),
            ],
        ],
    )
    rows = {row.player: row for row in standings(state)}
    assert rows[x].points_for == rows[y].points_for == 24
    assert (rows[x].wins, rows[y].wins) == (1, 0)
    assert rows[x].rank < rows[y].rank


def test_head_to_head_breaks_a_points_and_wins_tie() -> None:
    """A and B are level on points and wins; A took 20 off B, B took 4 off A."""
    players = roster(8)
    state = build(
        players,
        [
            [
                (("P01", "P03"), ("P02", "P04"), 20, 4),
                (("P05", "P06"), ("P07", "P08"), 12, 12),
            ],
            [
                (("P01", "P05"), ("P03", "P07"), 4, 20),
                (("P02", "P06"), ("P04", "P08"), 20, 4),
            ],
        ],
    )
    rows = {row.player: row for row in standings(state)}
    assert rows["P01"].points_for == rows["P02"].points_for == 24
    assert rows["P01"].wins == rows["P02"].wins == 1
    assert rows["P01"].rank < rows["P02"].rank


def test_draw_order_is_the_last_word() -> None:
    """With no results at all, nothing distinguishes anyone — the draw decides."""
    players = roster(8)
    shuffled = tuple(reversed(players))
    state = build(players, [], draw_order=shuffled)
    assert order_of(state) == list(shuffled)


def test_standings_can_be_taken_as_of_an_earlier_round() -> None:
    state = build(
        ("A", "B", "C", "D"),
        [
            [(("A", "B"), ("C", "D"), 20, 4)],
            [(("A", "C"), ("B", "D"), 0, 24)],
        ],
    )
    early = {row.player: row.points_for for row in standings(state, through_round=1)}
    late = {row.player: row.points_for for row in standings(state)}
    assert early["A"] == 20
    assert late["A"] == 20
    assert late["B"] == 20 + 24


def test_unplayed_matches_are_ignored() -> None:
    state = americano(8)
    assert all(row.played == 0 and row.points_for == 0 for row in standings(state))


def test_progression_tracks_cumulative_points() -> None:
    state = americano(8, seed=6)
    rng = Random(6)
    for number in range(1, 4):
        state = play_round(state, number, rng)

    series = progression(state)
    assert set(series) == set(state.players)

    final = {row.player: row.points_for for row in standings(state)}
    for player, points in series.items():
        assert [point.round_no for point in points] == [1, 2, 3]
        assert points[-1].cumulative_points == final[player]
        running = 0
        for point in points:
            running += point.points_for
            assert point.cumulative_points == running


def test_progression_records_rank_after_each_round() -> None:
    state = play_round(americano(8, seed=8), 1, Random(8))
    series = progression(state)
    ranks = {points[0].rank for points in series.values()}
    assert ranks == set(range(1, 9))


def test_progression_skips_rounds_with_no_results() -> None:
    state = americano(8, seed=2)
    state = play_round(state, 1, Random(2))
    state = play_round(state, 3, Random(3))
    series = progression(state)
    assert all([point.round_no for point in points] == [1, 3] for points in series.values())


def test_progression_is_empty_before_the_first_result() -> None:
    assert all(points == () for points in progression(americano(8)).values())
