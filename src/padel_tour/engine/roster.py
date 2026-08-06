"""Roster validation shared by both formats."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable

from .errors import DuplicatePlayer, InvalidPlayerCount
from .models import PlayerId


def validate_roster(players: Iterable[PlayerId]) -> tuple[PlayerId, ...]:
    """Normalise a roster to a tuple, rejecting duplicates and bad counts.

    Only multiples of four are allowed: with byes out of scope for now, an incomplete court
    has nowhere to go.
    """
    roster = tuple(players)

    duplicates = [player for player, count in Counter(roster).items() if count > 1]
    if duplicates:
        raise DuplicatePlayer(f"repeated in the roster: {', '.join(sorted(duplicates))}")

    if len(roster) < 4 or len(roster) % 4 != 0:
        raise InvalidPlayerCount(
            f"player count must be a multiple of 4 (4, 8, 12, 16, …) — got {len(roster)}"
        )

    return roster
