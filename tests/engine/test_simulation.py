"""Whole tournaments played out end to end, checking the invariants that must always hold."""

from __future__ import annotations

from random import Random

import pytest
from conftest import americano, mexicano, partner_counts, play_round
from hypothesis import given, settings
from hypothesis import strategies as st

from padel_tour.engine import (
    PairingPattern,
    TournamentState,
    is_played_out,
    next_round,
    progression,
    ranked_players,
    standings,
)


def assert_invariants(state: TournamentState) -> None:
    """Properties that hold for any played-out tournament of either format."""
    target = state.config.points_per_match
    played = [match for rnd in state.rounds for match in rnd.matches if match.played]

    # Each match hands out its full point target to each side's two players.
    total_awarded = sum(row.points_for for row in standings(state))
    assert total_awarded == 2 * target * len(played)

    # Points conceded mirror points scored.
    assert sum(row.points_against for row in standings(state)) == total_awarded

    rows = standings(state)
    assert [row.rank for row in rows] == list(range(1, len(state.players) + 1))
    assert {row.player for row in rows} == set(state.players)

    # Nobody sits out: every player appears once per round.
    for rnd in state.rounds:
        appearing = [player for match in rnd.matches for player in match.players()]
        assert sorted(appearing) == sorted(state.players)

    # The chart agrees with the table.
    final = {row.player: row.points_for for row in rows}
    for player, series in progression(state).items():
        if series:
            assert series[-1].cumulative_points == final[player]


def play_out_americano(size: int, seed: int) -> TournamentState:
    state = americano(size, seed=seed)
    rng = Random(seed)
    for number in range(1, state.total_rounds + 1):
        state = play_round(state, number, rng)
    return state


def play_out_mexicano(
    size: int, seed: int, rounds: int, pattern: PairingPattern
) -> TournamentState:
    state = mexicano(size, seed=seed, rounds=rounds, pattern=pattern)
    rng = Random(seed)
    for number in range(1, rounds + 1):
        if number > 1:
            state = next_round(state)
        state = play_round(state, number, rng)
    return state


@pytest.mark.parametrize("size", [4, 8, 12])
def test_full_americano(size: int) -> None:
    state = play_out_americano(size, seed=size)
    assert is_played_out(state)
    assert state.finished
    assert set(partner_counts(state).values()) == {1}
    assert_invariants(state)


@pytest.mark.parametrize("pattern", list(PairingPattern))
def test_full_mexicano(pattern: PairingPattern) -> None:
    state = play_out_mexicano(8, seed=13, rounds=6, pattern=pattern)
    assert is_played_out(state)
    assert state.finished
    assert_invariants(state)


def test_mexicano_courts_always_hold_adjacent_ranks() -> None:
    """The defining property: after every round, court k holds ranks 4k-3..4k."""
    state = mexicano(12, seed=3, rounds=5)
    rng = Random(3)
    for number in range(1, 6):
        if number > 1:
            order = ranked_players(state)
            state = next_round(state)
            for court, match in enumerate(state.rounds[-1].matches):
                assert set(match.players()) == set(order[court * 4 : court * 4 + 4])
        state = play_round(state, number, rng)


@settings(max_examples=25, deadline=None)
@given(scores=st.lists(st.integers(min_value=0, max_value=24), min_size=14, max_size=14))
def test_americano_invariants_hold_for_any_scores(scores: list[int]) -> None:
    from padel_tour.engine import record_result

    state = americano(8, seed=1)
    index = 0
    for rnd in state.rounds:
        for match in rnd.matches:
            score_a = scores[index]
            index += 1
            state = record_result(state, rnd.number, match.court, score_a, 24 - score_a)
    assert_invariants(state)


@settings(max_examples=25, deadline=None)
@given(seed=st.integers(min_value=0, max_value=10**6))
def test_any_seed_produces_a_balanced_americano(seed: int) -> None:
    assert set(partner_counts(americano(8, seed=seed)).values()) == {1}
