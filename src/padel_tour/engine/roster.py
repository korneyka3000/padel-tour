"""Roster validation shared by both formats."""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from .errors import DuplicatePlayerError, InvalidPlayerCountError
from .models import PLAYERS_PER_COURT

if TYPE_CHECKING:
    from collections.abc import Iterable

    from .models import PlayerId


def validate_roster(players: Iterable[PlayerId]) -> tuple[PlayerId, ...]:
    """Normalise a roster to a tuple, rejecting duplicates and bad counts.

    Only multiples of four are allowed: with byes out of scope for now, an incomplete court
    has nowhere to go.
    """
    roster = tuple(players)

    duplicates = [player for player, count in Counter(roster).items() if count > 1]
    if duplicates:
        raise DuplicatePlayerError(f"repeated in the roster: {', '.join(sorted(duplicates))}")

    if len(roster) < PLAYERS_PER_COURT or len(roster) % PLAYERS_PER_COURT != 0:
        raise InvalidPlayerCountError(
            f"player count must be a multiple of {PLAYERS_PER_COURT} "
            f"(4, 8, 12, 16, …) — got {len(roster)}"
        )

    return roster
