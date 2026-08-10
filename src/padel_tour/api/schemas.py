"""What the API puts on the wire.

Deliberately separate from the service layer's views. A ``TournamentView`` carries a whole
``TournamentState`` for callers that need to ask the engine something; none of that belongs
in JSON. Keeping the two apart also means the wire format can change without dragging the
service layer with it.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from padel_tour.engine import Format, PairingPattern
from padel_tour.services import (
    GroupView,
    PlayerView,
    RoundView,
    TournamentSummary,
    TournamentView,
    Viewing,
)


class Group(BaseModel):
    id: uuid.UUID
    name: str
    player_count: int

    @classmethod
    def of(cls, view: GroupView) -> Group:
        return cls(id=view.id, name=view.name, player_count=view.player_count)


class Player(BaseModel):
    id: uuid.UUID
    name: str
    is_active: bool

    @classmethod
    def of(cls, view: PlayerView) -> Player:
        return cls(id=view.id, name=view.name, is_active=view.is_active)


class GroupDetail(BaseModel):
    id: uuid.UUID
    name: str
    players: list[Player]
    is_owner: bool = Field(
        default=False,
        description="Whether the caller keeps this roster. Hides controls that would 403.",
    )


class Match(BaseModel):
    court: int
    team_a: tuple[str, str]
    team_b: tuple[str, str]
    score_a: int | None
    score_b: int | None
    team_a_ids: tuple[uuid.UUID, uuid.UUID] = Field(
        description="The same players by id, for deciding whether this court is yours to score"
    )
    team_b_ids: tuple[uuid.UUID, uuid.UUID]


class Round(BaseModel):
    number: int
    matches: list[Match]
    complete: bool

    @classmethod
    def of(cls, view: RoundView) -> Round:
        return cls(
            number=view.number,
            complete=view.complete,
            matches=[
                Match(
                    court=match.court,
                    team_a=match.team_a,
                    team_b=match.team_b,
                    score_a=match.score_a,
                    score_b=match.score_b,
                    team_a_ids=match.team_a_ids,
                    team_b_ids=match.team_b_ids,
                )
                for match in view.matches
            ],
        )


class Standing(BaseModel):
    rank: int
    player_id: uuid.UUID
    name: str
    played: int
    wins: int
    draws: int
    losses: int
    points_for: int
    points_against: int
    diff: int


class ProgressPoint(BaseModel):
    """One point on the round-by-round chart."""

    round_no: int
    points_for: int
    cumulative_points: int
    rank: int


class PlayerProgress(BaseModel):
    """One line on the chart, named so the client does not have to join anything."""

    player_id: uuid.UUID
    name: str
    points: list[ProgressPoint]


class Viewer(BaseModel):
    """Where the caller stands, so the screen can offer only what the server will accept.

    Four inputs rather than a verdict per match. The rule behind them lives in
    ``services.permissions.require_can_score`` and has branches the client cannot infer from
    a boolean — and a boolean per court would be one field per court, every one of them
    stale the moment a Mexicano draws its next round.
    """

    is_member: bool = False
    is_organiser: bool = False
    plays_as: uuid.UUID | None = Field(
        default=None, description="The player you are in this tournament, if you have claimed one"
    )
    anyone_may_score: bool = Field(
        default=False, description="No organiser, so the group scores it between them"
    )

    @classmethod
    def of(cls, seen: Viewing) -> Viewer:
        return cls(
            is_member=seen.is_member,
            is_organiser=seen.is_organiser,
            plays_as=seen.plays_as,
            anyone_may_score=seen.anyone_may_score,
        )


class Tournament(BaseModel):
    id: uuid.UUID
    group_id: uuid.UUID
    format: Format
    points_per_match: int
    pairing_pattern: PairingPattern
    total_rounds: int
    rounds_played: int
    finished: bool
    created_at: datetime
    finished_at: datetime | None
    rounds: list[Round]
    standings: list[Standing]
    progression: list[PlayerProgress]
    viewer: Viewer = Field(
        default_factory=Viewer,
        description="Defaults to a stranger, which is what a link-holder is",
    )

    @classmethod
    def of(cls, view: TournamentView, seen: Viewing | None = None) -> Tournament:
        return cls(
            viewer=Viewer() if seen is None else Viewer.of(seen),
            id=view.id,
            group_id=view.group_id,
            format=view.format,
            points_per_match=view.points_per_match,
            pairing_pattern=view.pairing_pattern,
            total_rounds=view.total_rounds,
            rounds_played=sum(1 for rnd in view.rounds if rnd.complete),
            finished=view.finished,
            created_at=view.created_at,
            finished_at=view.finished_at,
            rounds=[Round.of(rnd) for rnd in view.rounds],
            standings=[
                Standing(
                    rank=row.rank,
                    player_id=row.player_id,
                    name=row.name,
                    played=row.played,
                    wins=row.wins,
                    draws=row.draws,
                    losses=row.losses,
                    points_for=row.points_for,
                    points_against=row.points_against,
                    diff=row.diff,
                )
                for row in view.standings
            ],
            # Ordered by standing, so the chart's legend matches the table without the
            # client having to sort anything.
            progression=[
                PlayerProgress(
                    player_id=row.player_id,
                    name=row.name,
                    points=[
                        ProgressPoint(
                            round_no=point.round_no,
                            points_for=point.points_for,
                            cumulative_points=point.cumulative_points,
                            rank=point.rank,
                        )
                        for point in view.progression.get(row.player_id, ())
                    ],
                )
                for row in view.standings
            ],
        )


class TournamentCard(BaseModel):
    """An archive entry — enough for a list, no rounds or standings."""

    id: uuid.UUID
    format: Format
    finished: bool
    player_count: int
    rounds_played: int
    total_rounds: int
    created_at: datetime
    winner_name: str | None

    @classmethod
    def of(cls, summary: TournamentSummary) -> TournamentCard:
        return cls(
            id=summary.id,
            format=summary.format,
            finished=summary.finished,
            player_count=summary.player_count,
            rounds_played=summary.rounds_played,
            total_rounds=summary.total_rounds,
            created_at=summary.created_at,
            winner_name=summary.winner_name,
        )


class PlayerProfile(BaseModel):
    """A player's record across every tournament they have played."""

    id: uuid.UUID
    name: str
    tournaments: int
    matches: int
    wins: int
    points_for: int
    average_points: float = Field(description="Points per match played")
    best_rank: int | None
    podiums: int
    history: list[TournamentCard]


class Health(BaseModel):
    status: str
    database: str


class ErrorBody(BaseModel):
    """What a refusal looks like.

    Three fields because two audiences read it. ``detail`` is English and goes in the log;
    ``code`` and ``params`` let an interface say the same thing in its own language, with
    its own agreement rules. A client that does not know a code falls back to ``detail`` —
    an old page against a new server should show an awkward sentence, not an empty one.
    """

    detail: str
    code: str = ""
    params: dict[str, object] = Field(default_factory=dict)
