"""Mexicano: every round after the first is drawn from the standing."""

from __future__ import annotations

from dataclasses import replace
from random import Random

import pytest
from conftest import mexicano, play_round, roster

from padel_tour.engine import (
    Format,
    InvalidConfig,
    NoMoreRounds,
    PairingPattern,
    RoundIncomplete,
    TournamentConfig,
    TournamentFinished,
    WrongFormat,
    create_mexicano,
    finish,
    next_round,
    ranked_players,
    record_result,
    reroll,
)


def test_starts_with_a_single_round() -> None:
    state = mexicano(8)
    assert len(state.rounds) == 1
    assert state.total_rounds == 5
    assert len(state.rounds[0].matches) == 2


def test_opening_round_uses_everyone_once() -> None:
    state = mexicano(12)
    appearing = [player for match in state.rounds[0].matches for player in match.players()]
    assert sorted(appearing) == sorted(state.players)


def test_opening_round_is_random_not_roster_order() -> None:
    """Different seeds must produce different opening draws."""
    assert mexicano(8, seed=1).rounds[0] != mexicano(8, seed=2).rounds[0]


def test_next_round_requires_a_complete_current_round() -> None:
    state = record_result(mexicano(8), 1, 1, 14, 10)
    with pytest.raises(RoundIncomplete, match="unfinished"):
        next_round(state)


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        (PairingPattern.CROSSOVER, ((0, 3), (1, 2))),
        (PairingPattern.SPLIT, ((0, 2), (1, 3))),
        (PairingPattern.TOP_HEAVY, ((0, 1), (2, 3))),
    ],
)
def test_pattern_applied_to_the_standing(
    pattern: PairingPattern, expected: tuple[tuple[int, int], tuple[int, int]]
) -> None:
    state = mexicano(8, pattern=pattern)
    state = play_round(state, 1, Random(4))
    order = ranked_players(state)

    state = next_round(state)
    drawn = state.rounds[1]

    for court, match in enumerate(drawn.matches):
        group = order[court * 4 : court * 4 + 4]
        (a1, a2), (b1, b2) = expected
        assert match.team_a.as_set() == {group[a1], group[a2]}
        assert match.team_b.as_set() == {group[b1], group[b2]}


def test_leaders_share_the_first_court() -> None:
    """The point of Mexicano: ranks 1-4 meet on court 1, 5-8 on court 2."""
    state = play_round(mexicano(8), 1, Random(11))
    order = ranked_players(state)
    drawn = next_round(state).rounds[1]

    assert set(drawn.matches[0].players()) == set(order[:4])
    assert set(drawn.matches[1].players()) == set(order[4:])


def test_the_last_round_ends_the_tournament() -> None:
    """Scoring the final planned round finishes it — there is nothing left to draw."""
    state = mexicano(8, rounds=2)
    state = play_round(state, 1, Random(1))
    state = next_round(state)
    state = play_round(state, 2, Random(2))
    assert state.finished
    with pytest.raises(TournamentFinished):
        next_round(state)


def test_round_budget_is_enforced_independently_of_the_finished_flag() -> None:
    """Auto-finish normally gets there first; this guards the count on its own."""
    state = mexicano(8, rounds=2)
    state = play_round(state, 1, Random(1))
    state = next_round(state)
    state = play_round(state, 2, Random(2))
    with pytest.raises(NoMoreRounds, match="all 2 rounds"):
        next_round(replace(state, finished=False))


def test_next_round_after_finish_is_refused() -> None:
    state = finish(play_round(mexicano(8), 1, Random(1)))
    with pytest.raises(TournamentFinished):
        next_round(state)


def test_next_round_is_americano_nonsense() -> None:
    from conftest import americano

    with pytest.raises(WrongFormat):
        next_round(americano(8))


def test_mexicano_config_needs_a_round_count() -> None:
    with pytest.raises(InvalidConfig, match="number of rounds"):
        TournamentConfig(Format.MEXICANO)


def test_create_mexicano_rejects_an_americano_config() -> None:
    with pytest.raises(WrongFormat):
        create_mexicano(roster(8), TournamentConfig(Format.AMERICANO), seed=1)


def test_reroll_redraws_only_the_opening_round() -> None:
    original = mexicano(8, seed=5)
    rerolled = reroll(original)
    assert len(rerolled.rounds) == 1
    assert rerolled.rounds[0] != original.rounds[0]
    assert rerolled.players == original.players


def test_draw_is_reproducible_across_a_whole_run() -> None:
    """Same seed and same scores must replay to the same pairings, round after round."""

    def run() -> list[tuple[str, ...]]:
        state = mexicano(8, seed=21, rounds=4)
        pairings = []
        for number in range(1, 5):
            if number > 1:
                state = next_round(state)
            pairings.extend(match.players() for match in state.rounds[-1].matches)
            state = play_round(state, number, Random(number))
        return pairings

    assert run() == run()
