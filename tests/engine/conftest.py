"""Shared fixtures and helpers for engine tests."""

from __future__ import annotations

from collections import Counter
from random import Random

import pytest

from padel_tour.engine import (
    Format,
    PlayerId,
    TournamentConfig,
    TournamentState,
    create_americano,
    create_mexicano,
    record_result,
)


def roster(size: int) -> tuple[PlayerId, ...]:
    """A roster of ``size`` players named P01, P02, ... — sortable and unambiguous."""
    return tuple(f"P{index:02d}" for index in range(1, size + 1))


@pytest.fixture
def eight() -> tuple[PlayerId, ...]:
    return roster(8)


def americano(size: int = 8, *, seed: int = 1, points: int = 24) -> TournamentState:
    config = TournamentConfig(Format.AMERICANO, points_per_match=points)
    return create_americano(roster(size), config, seed)


def mexicano(
    size: int = 8, *, seed: int = 1, points: int = 24, rounds: int = 5, pattern=None
) -> TournamentState:
    kwargs = {} if pattern is None else {"pairing_pattern": pattern}
    config = TournamentConfig(Format.MEXICANO, points_per_match=points, rounds=rounds, **kwargs)
    return create_mexicano(roster(size), config, seed)


def partner_counts(state: TournamentState) -> Counter[frozenset[PlayerId]]:
    """How often each pair of players shared a team."""
    counts: Counter[frozenset[PlayerId]] = Counter()
    for rnd in state.rounds:
        for match in rnd.matches:
            counts[match.team_a.as_set()] += 1
            counts[match.team_b.as_set()] += 1
    return counts


def opponent_counts(state: TournamentState) -> Counter[frozenset[PlayerId]]:
    """How often each pair of players faced each other."""
    counts: Counter[frozenset[PlayerId]] = Counter()
    for rnd in state.rounds:
        for match in rnd.matches:
            for left in match.team_a:
                for right in match.team_b:
                    counts[frozenset((left, right))] += 1
    return counts


def play_round(state: TournamentState, round_no: int, rng: Random) -> TournamentState:
    """Fill in random but legal results for every court of a round."""
    target = state.config.points_per_match
    rnd = state.round_by_number(round_no)
    assert rnd is not None
    for match in rnd.matches:
        score_a = rng.randrange(target + 1)
        state = record_result(state, round_no, match.court, score_a, target - score_a)
    return state
