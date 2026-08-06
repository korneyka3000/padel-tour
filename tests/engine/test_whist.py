"""The whist design is the foundation of Americano — if it is wrong, nothing else matters."""

from __future__ import annotations

import pytest

from padel_tour.engine.errors import InvalidPlayerCount, UnsupportedPlayerCount
from padel_tour.engine.whist import (
    INF,
    STARTERS,
    design_defects,
    generate_from_starter,
    is_valid_whist_design,
    require_supported_player_count,
    search_starter,
    slots_for,
    supported_player_counts,
    whist_design,
)


@pytest.mark.parametrize("count", supported_player_counts())
def test_shipped_starter_generates_a_valid_design(count: int) -> None:
    """Guards against a typo in STARTERS reaching users."""
    assert design_defects(whist_design(count), count) == []


@pytest.mark.parametrize("count", supported_player_counts())
def test_design_shape(count: int) -> None:
    design = whist_design(count)
    assert len(design) == count - 1
    assert all(len(rnd) == count // 4 for rnd in design)


@pytest.mark.parametrize("count", supported_player_counts())
def test_every_slot_plays_once_per_round(count: int) -> None:
    expected = set(slots_for(count))
    for rnd in whist_design(count):
        appearing = [slot for game in rnd for pair in game for slot in pair]
        assert sorted(appearing) == sorted(expected)


def test_infinity_is_the_only_fixed_point() -> None:
    """Rotation must move every finite slot and leave INF alone."""
    design = whist_design(8)
    first_courts = [game for game in design[0]]
    second_courts = [game for game in design[1]]
    assert first_courts != second_courts
    inf_appearances = sum(
        1 for rnd in design for game in rnd for pair in game for slot in pair if slot == INF
    )
    assert inf_appearances == len(design)


@pytest.mark.parametrize("count", [0, 1, 5, 9, 14, -4])
def test_bad_player_counts_are_rejected(count: int) -> None:
    with pytest.raises(InvalidPlayerCount):
        require_supported_player_count(count)


def test_unknown_but_well_shaped_count_is_a_separate_error() -> None:
    """28 players is a legal shape we simply have no starter for — a different failure."""
    assert 28 not in STARTERS
    with pytest.raises(UnsupportedPlayerCount):
        require_supported_player_count(28)


def test_validator_catches_a_broken_starter() -> None:
    """A starter with a repeated partner difference must not pass."""
    broken = (((INF, 0), (1, 2)), ((3, 4), (5, 6)))
    defects = design_defects(generate_from_starter(broken, 8), 8)
    assert defects
    assert not is_valid_whist_design(generate_from_starter(broken, 8), 8)


@pytest.mark.parametrize("count", [4, 8, 12, 16])
def test_search_reproduces_a_valid_starter(count: int) -> None:
    """The search is the fallback for recomputing a starter, so it has to actually work."""
    found = search_starter(count)
    assert found is not None
    assert design_defects(generate_from_starter(found, count), count) == []


def test_search_rejects_counts_that_are_not_multiples_of_four() -> None:
    assert search_starter(10) is None
