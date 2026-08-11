"""What the service layer hands back to interfaces.

Views carry names, not just ids, and they carry the standings and the progression already
computed. If every interface called ``standings()`` and joined names itself, the bot and the
web would drift apart in small ways — a different tie-break here, a stale name there.
"""

from __future__ import annotations

# ruff would move these into a type-checking block, and they cannot go there: Pydantic
# resolves annotations when the class is built, and a name it cannot see turns into
# "PlayerView is not fully defined" at the first call rather than at import.
import uuid  # noqa: TC003
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from padel_tour.engine import (
        Format,
        PairingPattern,
        ProgressPoint,
        TournamentState,
    )


class GroupView(BaseModel):
    """A group, as everything above the database sees it.

    One schema, including on the wire. ``owner_account_id`` is internal — it is an account
    id, and no client has any use for it — so it is carried but never serialised. The
    alternative was a second near-identical class whose only job was to leave one field out,
    which is a duplicate with a standing invitation to drift.

    ``exclude`` is a serialisation setting, so the guarantee is only as good as nobody
    dumping this another way. That is what the test in ``tests/services/test_views.py``
    is for.
    """

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    #: Who runs the roster and hands out invitations. Unset for groups made from the CLI.
    owner_account_id: uuid.UUID | None = Field(default=None, exclude=True)
    #: Not on the row — counted alongside it.
    player_count: int = 0


class PlayerView(BaseModel):
    """A player, which is a row and nothing more.

    Pydantic rather than a dataclass, and read off the ORM object rather than assembled
    field by field. Two hand-written mappers used to build this — one in ``groups``, one in
    ``invites`` — for four fields that mirror the table exactly; the only thing they could
    ever do was disagree.

    ``model_validate`` still **copies**. It is not the same as handing an adapter the ORM
    row: touching an attribute nobody loaded, on an instance whose session has closed, is a
    ``MissingGreenlet`` far from where it was caused — and the bot and the CLI call these
    functions directly, with no HTTP layer to keep a session open around them.
    """

    model_config = ConfigDict(from_attributes=True)

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
    #: The same four players by id. Names are for reading; these are for deciding, and two
    #: people in a group may legitimately share one.
    team_a_ids: tuple[uuid.UUID, uuid.UUID]
    team_b_ids: tuple[uuid.UUID, uuid.UUID]

    @property
    def played(self) -> bool:
        return self.score_a is not None

    @property
    def player_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(self.team_a_ids + self.team_b_ids)


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
    #: Who runs this tournament. Unset for tournaments started from the CLI, which stay
    #: open to everyone rather than locked to nobody.
    organiser_account_id: uuid.UUID | None
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
    #: Everyone who played, best first.
    #:
    #: The archive used to carry only the winner, which made a line about eight people a
    #: line about one of them. Seven of the eight turned up, played every round, and were
    #: not mentioned.
    placings: tuple[str, ...] = ()
