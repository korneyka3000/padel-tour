"""Americano: the whole draw exists up front and is perfectly balanced."""

from __future__ import annotations

from random import Random

import pytest
from conftest import americano, opponent_counts, partner_counts, roster

from padel_tour.engine import (
    DuplicatePlayerError,
    Format,
    InvalidConfigError,
    InvalidPlayerCountError,
    RerollTooLateError,
    TournamentConfig,
    UnsupportedPlayerCountError,
    WrongFormatError,
    create_americano,
    record_result,
    reroll,
)


@pytest.mark.parametrize("size", [4, 8, 12, 16])
def test_full_cycle_length(size: int) -> None:
    state = americano(size)
    assert state.total_rounds == size - 1
    assert len(state.rounds) == size - 1
    assert state.court_count == size // 4


@pytest.mark.parametrize("size", [4, 8, 12, 16])
def test_everyone_partners_everyone_exactly_once(size: int) -> None:
    state = americano(size)
    counts = partner_counts(state)
    assert len(counts) == size * (size - 1) // 2
    assert set(counts.values()) == {1}


@pytest.mark.parametrize("size", [4, 8, 12])
def test_everyone_opposes_everyone_exactly_twice(size: int) -> None:
    assert set(opponent_counts(americano(size)).values()) == {2}


def test_everyone_plays_once_per_round() -> None:
    state = americano(12)
    for rnd in state.rounds:
        appearing = [player for match in rnd.matches for player in match.players()]
        assert sorted(appearing) == sorted(state.players)


def test_courts_are_numbered_from_one() -> None:
    state = americano(12)
    for rnd in state.rounds:
        assert [match.court for match in rnd.matches] == [1, 2, 3]


def test_same_seed_gives_the_same_draw() -> None:
    assert americano(8, seed=99).rounds == americano(8, seed=99).rounds


def test_different_seed_gives_a_different_but_equally_valid_draw() -> None:
    first, second = americano(8, seed=1), americano(8, seed=2)
    assert first.rounds != second.rounds
    assert set(partner_counts(second).values()) == {1}


def test_reroll_redraws_and_stays_balanced() -> None:
    original = americano(8, seed=5)
    rerolled = reroll(original)
    assert rerolled.rounds != original.rounds
    assert rerolled.players == original.players
    assert set(partner_counts(rerolled).values()) == {1}


def test_repeated_rerolls_are_reproducible() -> None:
    """The seed chain must be deterministic, or a replayed tournament diverges."""
    first = reroll(reroll(americano(8, seed=5)))
    second = reroll(reroll(americano(8, seed=5)))
    assert first.seed == second.seed
    assert first.rounds == second.rounds


def test_reroll_with_explicit_seed() -> None:
    assert reroll(americano(8, seed=5), seed=77).rounds == americano(8, seed=77).rounds


def test_reroll_is_refused_once_a_result_exists() -> None:
    state = record_result(americano(8), 1, 1, 14, 10)
    with pytest.raises(RerollTooLateError):
        reroll(state)


@pytest.mark.parametrize("size", [1, 5, 9, 11])
def test_player_count_must_be_a_multiple_of_four(size: int) -> None:
    with pytest.raises(InvalidPlayerCountError):
        americano(size)


def test_supported_but_unscheduled_count_is_reported_separately() -> None:
    with pytest.raises(UnsupportedPlayerCountError):
        create_americano(roster(28), TournamentConfig(Format.AMERICANO), seed=1)


def test_duplicate_players_are_rejected() -> None:
    with pytest.raises(DuplicatePlayerError):
        create_americano(
            ["A", "B", "C", "A", "E", "F", "G", "H"],
            TournamentConfig(Format.AMERICANO),
            seed=1,
        )


def test_americano_config_cannot_set_round_count() -> None:
    with pytest.raises(InvalidConfigError):
        TournamentConfig(Format.AMERICANO, rounds=5)


def test_create_americano_rejects_a_mexicano_config() -> None:
    with pytest.raises(WrongFormatError):
        create_americano(roster(8), TournamentConfig(Format.MEXICANO, rounds=3), seed=1)


def test_draw_order_is_a_permutation_of_the_roster() -> None:
    state = americano(12)
    assert sorted(state.draw_order) == sorted(state.players)


def test_schedule_is_stable_while_results_come_in() -> None:
    """Recording a score must never move anyone's future partners."""
    state = americano(8, seed=3)
    planned = [(match.team_a, match.team_b) for rnd in state.rounds for match in rnd.matches]
    rng = Random(0)
    for rnd in state.rounds:
        for match in rnd.matches:
            score = rng.randrange(25)
            state = record_result(state, rnd.number, match.court, score, 24 - score)
    actual = [(match.team_a, match.team_b) for rnd in state.rounds for match in rnd.matches]
    assert actual == planned
