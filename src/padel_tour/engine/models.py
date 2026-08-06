"""Immutable value types for the tournament engine.

Players are opaque string ids. Names, avatars and accounts live above the engine — the
engine only ever compares and orders ids.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import StrEnum

from .errors import InvalidConfig

PlayerId = str

#: Point targets offered by user interfaces. Not a validation whitelist — any target of at
#: least four points is accepted, these are just the ones organisers actually use.
COMMON_POINT_TARGETS: tuple[int, ...] = (16, 21, 24, 32)

#: Fewest points a match can be played to.
MIN_POINT_TARGET = 4


class Format(StrEnum):
    """Tournament format."""

    AMERICANO = "americano"
    MEXICANO = "mexicano"


class PairingPattern(StrEnum):
    """How a court's four ranked players are split into two teams.

    Numbers refer to standing within the group of four, 1 being the strongest.
    """

    #: 1+4 vs 2+3 — the de-facto Mexicano standard, gives the most even match.
    CROSSOVER = "crossover"
    #: 1+3 vs 2+4 — a common alternative.
    SPLIT = "split"
    #: 1+2 vs 3+4 — strongest pair against weakest pair.
    TOP_HEAVY = "top_heavy"


#: Index pairs for each pattern, applied to a group of four sorted by rank.
PATTERN_INDICES: dict[PairingPattern, tuple[tuple[int, int], tuple[int, int]]] = {
    PairingPattern.CROSSOVER: ((0, 3), (1, 2)),
    PairingPattern.SPLIT: ((0, 2), (1, 3)),
    PairingPattern.TOP_HEAVY: ((0, 1), (2, 3)),
}


@dataclass(frozen=True, slots=True)
class Team:
    """Two players sharing a side of the net for one match."""

    a: PlayerId
    b: PlayerId

    def __iter__(self) -> Iterator[PlayerId]:
        yield self.a
        yield self.b

    def __contains__(self, player: object) -> bool:
        return player == self.a or player == self.b

    def as_set(self) -> frozenset[PlayerId]:
        return frozenset((self.a, self.b))


@dataclass(frozen=True, slots=True)
class MatchResult:
    """Final score of a match, from team A's point of view."""

    score_a: int
    score_b: int


@dataclass(frozen=True, slots=True)
class Match:
    """One match on one court in one round."""

    court: int
    team_a: Team
    team_b: Team
    result: MatchResult | None = None

    @property
    def played(self) -> bool:
        return self.result is not None

    def players(self) -> tuple[PlayerId, PlayerId, PlayerId, PlayerId]:
        return (self.team_a.a, self.team_a.b, self.team_b.a, self.team_b.b)


@dataclass(frozen=True, slots=True)
class Round:
    """All matches played simultaneously, one per court."""

    number: int
    matches: tuple[Match, ...]

    @property
    def complete(self) -> bool:
        return all(match.played for match in self.matches)


@dataclass(frozen=True, slots=True)
class TournamentConfig:
    """Everything an organiser chooses before the first ball."""

    format: Format
    points_per_match: int = 24
    pairing_pattern: PairingPattern = PairingPattern.CROSSOVER
    #: Mexicano only. Americano always plays the full ``n - 1`` cycle.
    rounds: int | None = None

    def __post_init__(self) -> None:
        if self.points_per_match < MIN_POINT_TARGET:
            raise InvalidConfig(
                f"a match must run to at least {MIN_POINT_TARGET} points, "
                f"got {self.points_per_match}"
            )
        if self.format is Format.AMERICANO and self.rounds is not None:
            raise InvalidConfig(
                "an Americano runs a fixed n-1 rounds; its round count is not configurable"
            )
        if self.format is Format.MEXICANO:
            if self.rounds is None:
                raise InvalidConfig("a Mexicano has no natural end — set the number of rounds")
            if self.rounds < 1:
                raise InvalidConfig(f"need at least one round, got {self.rounds}")


@dataclass(frozen=True, slots=True)
class TournamentState:
    """The complete tournament. Every engine operation takes one and returns a new one."""

    config: TournamentConfig
    #: Roster in registration order.
    players: tuple[PlayerId, ...]
    #: Shuffled once at creation; the final, always-decisive tie-break.
    draw_order: tuple[PlayerId, ...]
    seed: int
    total_rounds: int
    rounds: tuple[Round, ...] = field(default_factory=tuple)
    finished: bool = False

    @property
    def court_count(self) -> int:
        return len(self.players) // 4

    @property
    def started(self) -> bool:
        """True once any result has been recorded."""
        return any(match.played for rnd in self.rounds for match in rnd.matches)

    @property
    def current_round(self) -> Round | None:
        """The latest generated round, or None before the tournament is set up."""
        return self.rounds[-1] if self.rounds else None

    def round_by_number(self, number: int) -> Round | None:
        for rnd in self.rounds:
            if rnd.number == number:
                return rnd
        return None


@dataclass(frozen=True, slots=True)
class StandingRow:
    """One line of the leaderboard."""

    rank: int
    player: PlayerId
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
class ProgressPoint:
    """One player's state after one round — a single point on the progression chart."""

    round_no: int
    points_for: int
    points_against: int
    cumulative_points: int
    rank: int
