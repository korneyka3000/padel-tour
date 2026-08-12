"""What the service layer hands back to interfaces.

Views carry names, not just ids, and they carry the standings and the progression already
computed. If every interface called ``standings()`` and joined names itself, the bot and the
web would drift apart in small ways — a different tie-break here, a stale name there.

**One class per thing, all the way to the wire.** There used to be a second set of models in
``api/schemas`` mirroring these field for field, plus the mappers to get from one to the
other: ``Tournament.of`` alone was fifty lines whose only possible behaviour was to agree
with the class above it. They are the same objects now. Where a view holds something a client
must not see — an account id, the engine's own state — the field is marked
``Field(exclude=True)`` and simply does not serialise.

That is the whole mechanism, and it is enough. There is no ``to_bot_api()`` or output mixin
here because nothing needs one: each of these has exactly one shape on the wire, and
``exclude`` produces it whether the caller is FastAPI, ``model_dump_json`` or a test. A
second serialisation method would be a second opinion about the same question.
"""

from __future__ import annotations

# ruff would move these into a type-checking block, and they cannot go there: Pydantic
# resolves annotations when the class is built, and a name it cannot see turns into
# "PlayerView is not fully defined" at the first call rather than at import.
import uuid  # noqa: TC003
from datetime import datetime  # noqa: TC003

from pydantic import BaseModel, ConfigDict, Field, InstanceOf, computed_field

from padel_tour.engine import (  # noqa: TC001 - see above
    Format,
    PairingPattern,
    TournamentState,
)


class View(BaseModel):
    """Base for everything below: read off ORM rows and engine objects by attribute.

    A single line, but repeated seven times it was seven chances for one class to be built
    a different way from its neighbours.
    """

    model_config = ConfigDict(from_attributes=True)


class GroupView(View):
    """A group, as everything above the database sees it.

    ``owner_account_id`` is internal — it is an account id, and no client has any use for it
    — so it is carried but never serialised. The alternative was a second near-identical
    class whose only job was to leave one field out, which is a duplicate with a standing
    invitation to drift.

    ``exclude`` is a serialisation setting, so the guarantee is only as good as nobody
    dumping this another way. That is what the test in ``tests/services/test_views.py``
    is for.
    """

    id: uuid.UUID
    name: str
    #: Who runs the roster and hands out invitations. Unset for groups made from the CLI.
    owner_account_id: uuid.UUID | None = Field(default=None, exclude=True)
    #: Not on the row — counted alongside it.
    player_count: int = 0


class PlayerView(View):
    """A player, which is a row and nothing more.

    Read off the ORM object rather than assembled field by field. Two hand-written mappers
    used to build this — one in ``groups``, one in ``invites`` — for four fields that mirror
    the table exactly; the only thing they could ever do was disagree.

    ``model_validate`` still **copies**. It is not the same as handing an adapter the ORM
    row: touching an attribute nobody loaded, on an instance whose session has closed, is a
    ``MissingGreenlet`` far from where it was caused — and the bot and the CLI call these
    functions directly, with no HTTP layer to keep a session open around them.
    """

    id: uuid.UUID
    group_id: uuid.UUID
    name: str
    is_active: bool

    #: Which account holds this player, if anybody does. Internal: an account id is not a
    #: client's business, and knowing one is not something roster membership should buy.
    account_id: uuid.UUID | None = Field(default=None, exclude=True)

    @computed_field
    @property
    def is_claimed(self) -> bool:
        """Whether a real person has attached themselves to this name.

        The fact, without the id. A roster needs it: an unclaimed player is a name somebody
        typed, and offering to invite a player who is already claimed is offering a button
        whose only outcome is a refusal from the server.
        """
        return self.account_id is not None


class MatchView(View):
    """A match with the four names filled in, ready to print."""

    court: int
    team_a: tuple[str, str]
    team_b: tuple[str, str]
    score_a: int | None
    score_b: int | None
    #: The same four players by id, for deciding whether this court is yours to score. Names
    #: are for reading; two people in a group may legitimately share one.
    team_a_ids: tuple[uuid.UUID, uuid.UUID]
    team_b_ids: tuple[uuid.UUID, uuid.UUID]

    @property
    def played(self) -> bool:
        return self.score_a is not None

    @property
    def player_ids(self) -> frozenset[uuid.UUID]:
        return frozenset(self.team_a_ids + self.team_b_ids)


class RoundView(View):
    number: int
    matches: tuple[MatchView, ...]

    @computed_field
    @property
    def complete(self) -> bool:
        """On the wire as well as in process — a client decides what to offer from it."""
        return all(match.played for match in self.matches)


class StandingView(View):
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

    @computed_field
    @property
    def diff(self) -> int:
        return self.points_for - self.points_against


class ProgressPointView(View):
    """One point on the round-by-round chart."""

    round_no: int
    points_for: int
    cumulative_points: int
    rank: int


class PlayerProgress(View):
    """One line on the chart, named so nobody has to join anything."""

    player_id: uuid.UUID
    name: str
    points: tuple[ProgressPointView, ...]


class Together(View):
    """How one player has fared alongside, or across the net from, another.

    The same shape answers both questions, because they are the same count from two sides:
    matches shared, and how many of them this player won. Which side of the net it was is the
    list it appears in, not a field.

    A win rate on its own is a trap at this scale — one match won together is 100% — so the
    count travels with it and the interface says both.
    """

    player_id: uuid.UUID
    name: str
    played: int
    won: int

    @computed_field
    @property
    def win_rate(self) -> float:
        return round(self.won / self.played, 3) if self.played else 0.0


class Viewing(View):
    """Where one caller stands in one tournament. All false is a stranger, and correct.

    Lives here rather than in ``permissions`` because it is a view: the *inputs* to
    :func:`~padel_tour.services.permissions.require_can_score`, not its verdict. A screen
    showing four courts needs to know which of them it may offer to score, and the honest way
    to tell it is to hand over what the rule reads — not a boolean per match, which would be
    one field per court, all of them stale the moment a Mexicano draws its next round.
    """

    is_member: bool = False
    is_organiser: bool = False
    plays_as: uuid.UUID | None = Field(
        default=None, description="The player you are in this tournament, if you have claimed one"
    )
    anyone_may_score: bool = Field(
        default=False, description="No organiser, so the group scores it between them"
    )


class TournamentView(View):
    """Everything an interface needs to render a tournament — and it is the JSON, too."""

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
    #: Ordered by standing, so a chart's legend matches the table with nothing to sort.
    #:
    #: A mapping once, which meant every consumer — the CLI, the bot's chart, the API — wrote
    #: the same loop over ``standings`` to put it in this order and attach the names. Three
    #: copies of one join.
    progression: tuple[PlayerProgress, ...]

    #: Who runs this tournament. Unset for tournaments started from the CLI, which stay open
    #: to everyone rather than locked to nobody. Internal: it is an account id.
    organiser_account_id: uuid.UUID | None = Field(default=None, exclude=True)
    #: The engine's own state, for callers needing to ask it something the fields above do
    #: not already answer. Internal, and ``InstanceOf`` so Pydantic checks the type rather
    #: than rebuilding an object graph it has no business copying.
    state: InstanceOf[TournamentState] = Field(exclude=True, repr=False)

    viewer: Viewing = Field(
        default_factory=Viewing,
        description="Defaults to a stranger, which is what a link-holder is",
    )

    @computed_field
    @property
    def rounds_played(self) -> int:
        return sum(1 for rnd in self.rounds if rnd.complete)

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

    def seen_by(self, seen: Viewing) -> TournamentView:
        """The same tournament, told from one caller's side.

        A copy rather than an assignment: who is asking is a property of the request, and a
        view that changed under one caller because another arrived would be a cache bug
        waiting for two of them at once.
        """
        return self.model_copy(update={"viewer": seen})


class TournamentSummary(View):
    """A line in a list of past tournaments — no rounds, no standings, one query."""

    id: uuid.UUID
    format: Format
    finished: bool
    player_count: int
    rounds_played: int
    total_rounds: int
    created_at: datetime
    winner_name: str | None

    #: Which group it belongs to. The caller asked about a group, so telling them again is
    #: noise; the bot uses it to route a button.
    group_id: uuid.UUID = Field(exclude=True)
    #: The group's name, filled in only where a list spans more than one — "my tournaments"
    #: is otherwise a column of formats and dates with no way to tell them apart.
    group_name: str | None = None
    #: Where the person asking finished. ``None`` when nobody is asking in particular, or
    #: when they were not in this one.
    my_rank: int | None = None
    finished_at: datetime | None = Field(default=None, exclude=True)
    #: Everyone who played, best first.
    #:
    #: The archive used to carry only the winner, which made a line about eight people a line
    #: about one of them. Seven of the eight turned up, played every round, and were not
    #: mentioned. Excluded only because the web's archive has no room to show it yet.
    placings: tuple[str, ...] = Field(default=(), exclude=True)
