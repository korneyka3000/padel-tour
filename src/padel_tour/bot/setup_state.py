"""The half-finished choices made before a tournament exists.

Picking a roster and choosing settings happen before there is anything in the database to
attach them to, so they live in memory, keyed by chat. Losing them on restart is harmless:
the organiser starts the selection again. Everything about a tournament that has actually
begun is in the database and survives.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from padel_tour.engine import Format, PairingPattern, TournamentConfig
from padel_tour.engine.whist import supported_player_counts

if TYPE_CHECKING:
    import uuid

#: Sensible defaults: the most common match length, and the standard Mexicano crossover.
DEFAULT_POINTS = 24
PLAYERS_PER_COURT = 4


@dataclass(slots=True)
class Draft:
    """A tournament being assembled in a chat."""

    group_id: uuid.UUID
    selected: set[uuid.UUID] = field(default_factory=set)
    format: Format = Format.AMERICANO
    points_per_match: int = DEFAULT_POINTS
    pairing_pattern: PairingPattern = PairingPattern.CROSSOVER
    rounds: int | None = None

    def toggle(self, player_id: uuid.UUID) -> None:
        self.selected.symmetric_difference_update({player_id})

    def allowed_counts(self) -> tuple[int, ...]:
        """Player counts this format can schedule.

        Americano needs a whist design, which exists only for the counts we ship. A Mexicano
        draws each round from the standing, so any multiple of four works.
        """
        if self.format is Format.AMERICANO:
            return supported_player_counts()
        return tuple(range(PLAYERS_PER_COURT, 41, PLAYERS_PER_COURT))

    @property
    def ready(self) -> bool:
        return len(self.selected) in self.allowed_counts()

    @property
    def default_rounds(self) -> int:
        return max(1, len(self.selected) - 1)

    def config(self) -> TournamentConfig:
        if self.format is Format.AMERICANO:
            return TournamentConfig(self.format, points_per_match=self.points_per_match)
        return TournamentConfig(
            self.format,
            points_per_match=self.points_per_match,
            pairing_pattern=self.pairing_pattern,
            rounds=self.rounds or self.default_rounds,
        )


class DraftStore:
    """Drafts in flight, one per chat."""

    def __init__(self) -> None:
        self._drafts: dict[int, Draft] = {}

    def start(self, chat_id: int, group_id: uuid.UUID) -> Draft:
        draft = Draft(group_id=group_id)
        self._drafts[chat_id] = draft
        return draft

    def get(self, chat_id: int) -> Draft | None:
        return self._drafts.get(chat_id)

    def clear(self, chat_id: int) -> None:
        self._drafts.pop(chat_id, None)
