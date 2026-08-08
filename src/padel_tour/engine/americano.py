"""Americano — the whole schedule is drawn before the first ball.

Every player partners every other player exactly once over n−1 rounds. The schedule itself
is a fixed whist design; the draw is nothing more than a random seating of players into its
slots. That is why a reroll can never produce a worse schedule — only a different one.
"""

from __future__ import annotations

from random import Random
from typing import TYPE_CHECKING

from .errors import WrongFormatError
from .models import Format, Match, PlayerId, Round, Team, TournamentConfig, TournamentState
from .roster import validate_roster
from .whist import require_supported_player_count, slots_for, whist_design

if TYPE_CHECKING:
    from collections.abc import Iterable


def create_americano(
    players: Iterable[PlayerId], config: TournamentConfig, seed: int
) -> TournamentState:
    """Draw a complete Americano.

    ``seed`` is stored on the state and drives every random choice, so the same seed and
    roster always produce the same schedule.
    """
    if config.format is not Format.AMERICANO:
        raise WrongFormatError(f"create_americano called with format {config.format}")

    roster = validate_roster(players)
    require_supported_player_count(len(roster))

    rng = Random(seed)
    draw_order = tuple(rng.sample(roster, len(roster)))

    seating = list(roster)
    rng.shuffle(seating)
    slot_to_player = dict(zip(slots_for(len(roster)), seating, strict=True))

    rounds = tuple(
        Round(
            number=number,
            matches=tuple(
                Match(
                    court=court,
                    team_a=Team(slot_to_player[a], slot_to_player[b]),
                    team_b=Team(slot_to_player[c], slot_to_player[d]),
                )
                for court, ((a, b), (c, d)) in enumerate(slot_round, start=1)
            ),
        )
        for number, slot_round in enumerate(whist_design(len(roster)), start=1)
    )

    return TournamentState(
        config=config,
        players=roster,
        draw_order=draw_order,
        seed=seed,
        total_rounds=len(roster) - 1,
        rounds=rounds,
    )
