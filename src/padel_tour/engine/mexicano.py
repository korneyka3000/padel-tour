"""Mexicano — each round is drawn from the standing that precedes it.

Round one is random because there is nothing to rank yet. From then on the leaderboard is
cut into fours — ranks 1-4 to court 1, 5-8 to court 2 — and each four is split by the
configured pattern, ``1+4 vs 2+3`` by default.
"""

from __future__ import annotations

from dataclasses import replace
from random import Random
from typing import TYPE_CHECKING

from .errors import (
    InvalidConfigError,
    NoMoreRoundsError,
    RoundIncompleteError,
    TournamentFinishedError,
    WrongFormatError,
)
from .models import (
    PATTERN_INDICES,
    Format,
    Match,
    PairingPattern,
    PlayerId,
    Round,
    Team,
    TournamentConfig,
    TournamentState,
)
from .roster import validate_roster
from .standings import ranked_players

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence


def draw_round(number: int, order: Sequence[PlayerId], pattern: PairingPattern) -> Round:
    """Cut an ordered roster into courts of four and split each by ``pattern``."""
    (first, second), (third, fourth) = PATTERN_INDICES[pattern]
    return Round(
        number=number,
        matches=tuple(
            Match(
                court=court,
                team_a=Team(group[first], group[second]),
                team_b=Team(group[third], group[fourth]),
            )
            for court, group in enumerate(
                (order[start : start + 4] for start in range(0, len(order), 4)), start=1
            )
        ),
    )


def create_mexicano(
    players: Iterable[PlayerId], config: TournamentConfig, seed: int
) -> TournamentState:
    """Start a Mexicano with a random first round. Later rounds come from :func:`next_round`."""
    if config.format is not Format.MEXICANO:
        raise WrongFormatError(f"create_mexicano called with format {config.format}")

    roster = validate_roster(players)
    if config.rounds is None:  # TournamentConfig guarantees this; narrow it for the reader
        raise InvalidConfigError("a Mexicano needs a round count")

    rng = Random(seed)
    draw_order = tuple(rng.sample(roster, len(roster)))

    opening = list(roster)
    rng.shuffle(opening)

    return TournamentState(
        config=config,
        players=roster,
        draw_order=draw_order,
        seed=seed,
        total_rounds=config.rounds,
        rounds=(draw_round(1, opening, config.pairing_pattern),),
    )


def next_round(state: TournamentState) -> TournamentState:
    """Draw the next round from the current standing.

    Requires the current round to be complete — the standing is meaningless while a court is
    still playing, and drawing from it would hand out the wrong partners.
    """
    if state.config.format is not Format.MEXICANO:
        raise WrongFormatError("only a Mexicano draws its rounds one at a time")
    if state.finished:
        raise TournamentFinishedError("the tournament is over")

    current = state.current_round
    if current is not None and not current.complete:
        pending = [match.court for match in current.matches if not match.played]
        raise RoundIncompleteError(
            f"round {current.number} is unfinished — no result on court "
            f"{', '.join(str(court) for court in pending)}"
        )
    if len(state.rounds) >= state.total_rounds:
        raise NoMoreRoundsError(f"all {state.total_rounds} rounds have been played")

    order = ranked_players(state)
    drawn = draw_round(len(state.rounds) + 1, order, state.config.pairing_pattern)
    return replace(state, rounds=(*state.rounds, drawn))
