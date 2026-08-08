"""What the service layer hands back to interfaces.

Views carry names, not just ids, and they carry the standings and the progression already
computed. If every interface called ``standings()`` and joined names itself, the bot and the
web would drift apart in small ways — a different tie-break here, a stale name there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import uuid
    from datetime import datetime

    from padel_tour.engine import (
        Format,
        PairingPattern,
        ProgressPoint,
        TournamentState,
    )


@dataclass(frozen=True, slots=True)
class GroupView:
    id: uuid.UUID
    name: str
    telegram_chat_id: int | None
    player_count: int


@dataclass(frozen=True, slots=True)
class PlayerView:
    id: uuid.UUID
    group_id: uuid.UUID
    name: str
    is_active: bool


@dataclass(frozen=True, slots=True)
class MatchView:
    """A match with the four names filled in, ready to print."""

    court: int
    team_a: tuple[str, str]
    team_b: tuple[str, str]
    score_a: int | None
    score_b: int | None

    @property
    def played(self) -> bool:
        return self.score_a is not None


@dataclass(frozen=True, slots=True)
class RoundView:
    number: int
    matches: tuple[MatchView, ...]

    @property
    def complete(self) -> bool:
        return all(match.played for match in self.matches)


@dataclass(frozen=True, slots=True)
class StandingView:
    """One leaderboard line, named."""

    rank: int
    player_id: uuid.UUID
    name: str
    played: int
    wins: int
    draws: int
    losses: int
    points_for: int
    points_against: int

    @property
    def diff(self) -> int:
        return self.points_for - self.points_against


@dataclass(frozen=True, slots=True)
class TournamentView:
    """Everything an interface needs to render a tournament.

    ``state`` is kept for callers that need to ask the engine something the view does not
    already answer; the fields above it cover every ordinary case.
    """

    id: uuid.UUID
    group_id: uuid.UUID
    format: Format
    points_per_match: int
    pairing_pattern: PairingPattern
    total_rounds: int
    finished: bool
    created_at: datetime
    finished_at: datetime | None
    rounds: tuple[RoundView, ...]
    standings: tuple[StandingView, ...]
    progression: dict[uuid.UUID, tuple[ProgressPoint, ...]]
    state: TournamentState

    @property
    def current_round(self) -> RoundView | None:
        return self.rounds[-1] if self.rounds else None

    @property
    def next_unfinished_round(self) -> RoundView | None:
        return next((rnd for rnd in self.rounds if not rnd.complete), None)

    def name_of(self, player_id: uuid.UUID) -> str:
        for row in self.standings:
            if row.player_id == player_id:
                return row.name
        return str(player_id)


@dataclass(frozen=True, slots=True)
class TournamentSummary:
    """A line in a list of past tournaments — no rounds, no standings, one query."""

    id: uuid.UUID
    group_id: uuid.UUID
    format: Format
    finished: bool
    player_count: int
    rounds_played: int
    total_rounds: int
    created_at: datetime
    finished_at: datetime | None
    winner_name: str | None
