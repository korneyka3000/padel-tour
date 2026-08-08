"""Recording, amending and ending — the operations shared by both formats."""

from __future__ import annotations

from random import Random

import pytest
from conftest import americano, play_round

from padel_tour.engine import (
    InvalidScoreError,
    ResultAlreadyRecordedError,
    TournamentFinishedError,
    UnknownMatchError,
    amend_result,
    finish,
    is_played_out,
    pending_matches,
    record_result,
    standings,
)


def test_score_must_add_up_to_the_target() -> None:
    with pytest.raises(InvalidScoreError, match="runs to 24 points"):
        record_result(americano(8), 1, 1, 15, 10)


def test_negative_scores_are_rejected() -> None:
    with pytest.raises(InvalidScoreError):
        record_result(americano(8), 1, 1, -1, 25)


def test_shutout_is_a_legal_score() -> None:
    state = record_result(americano(8), 1, 1, 24, 0)
    assert state.rounds[0].matches[0].result is not None


def test_custom_point_target() -> None:
    state = americano(8, points=32)
    with pytest.raises(InvalidScoreError, match="runs to 32 points"):
        record_result(state, 1, 1, 14, 10)
    assert record_result(state, 1, 1, 18, 14).started


def test_unknown_round_and_court() -> None:
    state = americano(8)
    with pytest.raises(UnknownMatchError, match="round 99"):
        record_result(state, 99, 1, 14, 10)
    with pytest.raises(UnknownMatchError, match="no court 7"):
        record_result(state, 1, 7, 14, 10)


def test_a_result_cannot_be_recorded_twice() -> None:
    state = record_result(americano(8), 1, 1, 14, 10)
    with pytest.raises(ResultAlreadyRecordedError, match="amend_result"):
        record_result(state, 1, 1, 12, 12)


def test_amend_fixes_a_typo_and_the_table_follows() -> None:
    state = record_result(americano(8, seed=4), 1, 1, 24, 0)
    winners = state.rounds[0].matches[0].team_a
    before = {row.player: row.points_for for row in standings(state)}
    assert before[winners.a] == 24

    state = amend_result(state, 1, 1, 13, 11)
    after = {row.player: row.points_for for row in standings(state)}
    assert after[winners.a] == 13


def test_amend_still_validates_the_score() -> None:
    state = record_result(americano(8), 1, 1, 14, 10)
    with pytest.raises(InvalidScoreError):
        amend_result(state, 1, 1, 20, 20)


def test_recording_is_refused_after_the_tournament_ends() -> None:
    state = finish(americano(8))
    with pytest.raises(TournamentFinishedError):
        record_result(state, 1, 1, 14, 10)


def test_the_last_result_finishes_the_tournament() -> None:
    state = americano(4, seed=2)
    assert not state.finished
    rng = Random(2)
    for number in range(1, 4):
        state = play_round(state, number, rng)
    assert is_played_out(state)
    assert state.finished


def test_finishing_early_keeps_the_standing() -> None:
    """Eleven rounds is a long evening — stopping early has to be normal."""
    state = play_round(americano(12), 1, Random(1))
    before = standings(state)
    stopped = finish(state)
    assert stopped.finished
    assert standings(stopped) == before


def test_pending_matches_drains_as_results_arrive() -> None:
    state = americano(8)
    assert len(pending_matches(state)) == 7 * 2
    state = record_result(state, 1, 1, 14, 10)
    pending = pending_matches(state)
    assert len(pending) == 13
    assert (1, state.rounds[0].matches[0]) not in pending


def test_state_is_never_mutated_in_place() -> None:
    original = americano(8)
    record_result(original, 1, 1, 14, 10)
    assert not original.started
