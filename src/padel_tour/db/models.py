"""ORM models.

The constraints here are load-bearing. Anything the database can refuse outright — a
duplicate player name, half a score, two players in the same draw position — is refused
here rather than trusted to careful calling code.

Types stay portable: tests run on SQLite locally and Postgres in CI, so nothing
Postgres-specific appears unless it earns its keep.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

# Imported at runtime on purpose: SQLAlchemy resolves `Mapped[...]` annotations when it maps
# the class, so moving these into a TYPE_CHECKING block makes every model fail to map.
from padel_tour.engine import Format, PairingPattern

#: Longest name we accept for a group or player. Generous for real names, short enough that
#: a Telegram keyboard row stays readable.
NAME_LENGTH = 100

#: Longest external identifier we store. An email address is the long case.
EXTERNAL_ID_LENGTH = 320

#: How someone signs in, or how a group is reached from outside. Our `Account` is the
#: identity; these are only ways of arriving at it, which is what keeps a second
#: integration from reshaping the domain.
PROVIDER_EMAIL = "email"
PROVIDER_TELEGRAM = "telegram"


def new_id() -> uuid.UUID:
    """A fresh time-ordered primary key.

    UUIDv7 sorts by creation time, so inserts land at the end of the index instead of
    scattering across it the way UUIDv4 does.
    """
    return uuid.uuid7()


def utc_now() -> datetime:
    return datetime.now(UTC)


class UtcDateTime(TypeDecorator[datetime]):
    """A timestamp that is timezone-aware UTC on every dialect.

    Postgres ``timestamptz`` returns aware datetimes; SQLite has no timezone type at all and
    returns naive ones. Without normalising, the same code compares equal locally and not in
    CI. Values go in as UTC and come out as UTC, and application code never has to ask which
    database it is talking to.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: object) -> datetime | None:  # noqa: ARG002
        if value is None:
            return None
        if value.tzinfo is None:
            raise ValueError("refusing to store a naive datetime; pass an aware one")
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect: object) -> datetime | None:  # noqa: ARG002
        if value is None:
            return None
        # A naive value can only have come from a dialect that discards the offset, and
        # everything we write is UTC.
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


#: Every relationship is declared ``lazy="raise_on_sql"``, and that is a rule rather than a
#: tuning choice: a query states what it needs or it fails, loudly, where it was written.
#:
#: The alternative is not "sometimes a bit slower". It is an N+1 that nobody sees until the
#: group has twenty players, plus — because these sessions are async — a ``MissingGreenlet``
#: raised far from whatever forgot to load, on an object whose session has already closed.
#: ``raise_on_sql`` rather than ``raise``: an attribute that is already loaded, or reachable
#: without touching the database, still just works.


class Base(DeclarativeBase):
    """Declarative base for every table."""


class TournamentStatus:
    """Lifecycle of a tournament. Plain strings — the set is tiny and stable."""

    ACTIVE = "active"
    FINISHED = "finished"


class Account(Base):
    """A person, as our system knows them.

    Deliberately almost empty. Everything about *how* they sign in lives in `identities`,
    so adding a provider never touches this table or anything that references it.
    """

    __tablename__ = "accounts"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    display_name: Mapped[str | None] = mapped_column(String(NAME_LENGTH), default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())

    identities: Mapped[list[Identity]] = relationship(
        lazy="raise_on_sql", back_populates="account", cascade="all, delete-orphan"
    )


class Identity(Base):
    """One way of signing in to an account: an email address, a Telegram user, later more."""

    __tablename__ = "identities"
    __table_args__ = (
        # One external login leads to one account, or the same Telegram user could sign in
        # as two different people.
        Index("uq_identity_external", "provider", "external_id", unique=True),
        # And one account has at most one login per provider.
        Index("uq_identity_provider", "account_id", "provider", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(EXTERNAL_ID_LENGTH))
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())

    account: Mapped[Account] = relationship(lazy="raise_on_sql", back_populates="identities")


class LoginSession(Base):
    """An active sign-in.

    Named for the table rather than for `Session`, which every module here already means
    as a database session.

    Server-side rather than a signed token, and that is the design rather than a step
    towards one. A JWT would save the lookup below — but every endpoint here reads the
    database anyway, so there is no lookup to save, and the price would be that a stolen
    token stays valid until it expires. These rows can be deleted: one device, or all of
    them, immediately.
    """

    __tablename__ = "sessions"
    __table_args__ = (
        Index("uq_session_token", "token_hash", unique=True),
        # The purge on sign-in filters on this column across the whole table.
        Index("ix_sessions_last_used_at", "last_used_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    account_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("accounts.id", ondelete="CASCADE"))
    #: Only ever the hash. A leaked database does not let anyone sign in.
    token_hash: Mapped[str] = mapped_column(String(64))
    #: The absolute deadline, fixed when the session opens. Never extended — a session that
    #: renewed itself on use would have no deadline at all.
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    #: The other deadline: go quiet for long enough and the session dies early. Without it a
    #: cookie copied off a laptop is good for the whole thirty days, whether or not its owner
    #: ever comes back. Written lazily — see ``TOUCH_AFTER`` in ``services.accounts``.
    last_used_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())


class MagicLink(Base):
    """A single-use sign-in link.

    Usually sent to an email address, which is what ``email`` is for. It can instead be
    bound to an account that is already known — the bot handing somebody a way into the web
    when it already knows who they are, with no mail server involved. Exactly one of the two
    is meaningful for any given link.
    """

    __tablename__ = "magic_links"
    __table_args__ = (Index("uq_magic_token", "token_hash", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(EXTERNAL_ID_LENGTH))
    #: Set when the link was issued to somebody already identified, in which case redeeming
    #: it signs in as this account rather than resolving an address.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="CASCADE"), default=None
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())


class Invite(Base):
    """An invitation to become one specific player.

    Issued against a player rather than a group, which is what makes claiming someone
    else's history impossible.
    """

    __tablename__ = "invites"
    __table_args__ = (Index("uq_invite_token", "token_hash", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    player_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    created_by_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), default=None
    )
    token_hash: Mapped[str] = mapped_column(String(64))
    expires_at: Mapped[datetime] = mapped_column(UtcDateTime)
    used_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())


class GroupLink(Base):
    """Where a group is reachable from outside — a Telegram chat, later something else."""

    __tablename__ = "group_links"
    __table_args__ = (
        Index("uq_group_link_external", "provider", "external_id", unique=True),
        Index("uq_group_link_provider", "group_id", "provider", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    provider: Mapped[str] = mapped_column(String(20))
    external_id: Mapped[str] = mapped_column(String(EXTERNAL_ID_LENGTH))

    group: Mapped[Group] = relationship(lazy="raise_on_sql", back_populates="links")


class Group(Base):
    """A padel community: a chat, a club, a regular Tuesday crowd."""

    __tablename__ = "groups"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(NAME_LENGTH), unique=True)
    #: Who runs the roster and hands out invitations.
    owner_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), default=None
    )
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())

    players: Mapped[list[Player]] = relationship(
        lazy="raise_on_sql", back_populates="group", cascade="all, delete-orphan"
    )
    links: Mapped[list[GroupLink]] = relationship(
        lazy="raise_on_sql", back_populates="group", cascade="all, delete-orphan"
    )
    tournaments: Mapped[list[Tournament]] = relationship(
        lazy="raise_on_sql", back_populates="group", cascade="all, delete-orphan"
    )


class Player(Base):
    """Someone who plays. Deliberately not an account — see the roadmap.

    Players are never deleted, only deactivated: a person who leaves the group still has to
    appear in the tournaments they played, or the history stops adding up.
    """

    __tablename__ = "players"
    __table_args__ = (
        Index("uq_players_group_name", "group_id", "name", unique=True),
        # One person is one player per group. Unclaimed players are the normal case, and
        # a partial index lets any number of them coexist.
        Index(
            "uq_players_group_account",
            "group_id",
            "account_id",
            unique=True,
            postgresql_where=text("account_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    name: Mapped[str] = mapped_column(String(NAME_LENGTH))
    #: A player exists without one; signing up is never a condition of playing. Deleting
    #: an account leaves the player and their history in place.
    account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), default=None
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())

    group: Mapped[Group] = relationship(lazy="raise_on_sql", back_populates="players")


class Tournament(Base):
    """One event. Settings are frozen at creation; the engine replays from them."""

    __tablename__ = "tournaments"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    group_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("groups.id", ondelete="CASCADE"))
    format: Mapped[Format] = mapped_column(String(20))
    points_per_match: Mapped[int] = mapped_column(Integer)
    pairing_pattern: Mapped[PairingPattern] = mapped_column(String(20))
    total_rounds: Mapped[int] = mapped_column(Integer)
    #: Drives every random choice the engine makes, so a tournament is reproducible.
    #: BigInteger, not Integer: seeds are unsigned 32-bit and Postgres INTEGER is signed,
    #: so anything above 2**31 is rejected there while SQLite accepts it happily.
    seed: Mapped[int] = mapped_column(BigInteger)
    status: Mapped[str] = mapped_column(String(20), default=TournamentStatus.ACTIVE)
    created_at: Mapped[datetime] = mapped_column(UtcDateTime, server_default=func.now())
    finished_at: Mapped[datetime | None] = mapped_column(UtcDateTime, default=None)

    #: The single Telegram message the bot keeps redrawing for this tournament. Storing it
    #: is what lets a restarted bot pick up the same screen instead of posting a new one.
    screen_chat_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    screen_message_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    #: The chart, which has to be its own message.
    #:
    #: Telegram cannot turn a text message into a photo one, so the picture cannot live in
    #: the screen above. It gets a second message that is replaced while it is on show and
    #: deleted the moment the chat navigates away — two messages at most, never a running
    #: commentary. Stored rather than remembered in memory: the bot is serverless in
    #: production and would otherwise leave an orphan photo behind on every cold start.
    chart_message_id: Mapped[int | None] = mapped_column(BigInteger, default=None)
    #: Who runs this tournament. Per tournament, not per group: last week it was one
    #: person, this week another.
    organiser_account_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("accounts.id", ondelete="SET NULL"), default=None
    )

    group: Mapped[Group] = relationship(lazy="raise_on_sql", back_populates="tournaments")
    entries: Mapped[list[TournamentPlayer]] = relationship(
        lazy="raise_on_sql",
        back_populates="tournament",
        cascade="all, delete-orphan",
        order_by="TournamentPlayer.draw_position",
    )
    rounds: Mapped[list[Round]] = relationship(
        lazy="raise_on_sql",
        back_populates="tournament",
        cascade="all, delete-orphan",
        order_by="Round.number",
    )


class TournamentPlayer(Base):
    """A player's entry in a tournament, plus where the draw put them.

    ``draw_position`` is the engine's final tie-break. It is stored rather than recomputed
    from the seed so that changing how we shuffle can never reorder a finished tournament.
    """

    __tablename__ = "tournament_players"
    __table_args__ = (Index("uq_entry_position", "tournament_id", "draw_position", unique=True),)

    tournament_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE"), primary_key=True
    )
    player_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("players.id", ondelete="RESTRICT"), primary_key=True
    )
    draw_position: Mapped[int] = mapped_column(Integer)

    tournament: Mapped[Tournament] = relationship(lazy="raise_on_sql", back_populates="entries")
    player: Mapped[Player] = relationship(lazy="raise_on_sql")


class Round(Base):
    """All matches played at the same time, one per court."""

    __tablename__ = "rounds"
    __table_args__ = (Index("uq_round_number", "tournament_id", "number", unique=True),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    tournament_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("tournaments.id", ondelete="CASCADE")
    )
    number: Mapped[int] = mapped_column(Integer)

    tournament: Mapped[Tournament] = relationship(lazy="raise_on_sql", back_populates="rounds")
    matches: Mapped[list[Match]] = relationship(
        lazy="raise_on_sql",
        back_populates="round",
        cascade="all, delete-orphan",
        order_by="Match.court",
    )


class Match(Base):
    """One court in one round.

    Teams are stored as four player ids rather than a join table: a padel match is always
    exactly two on two, so a variable-length relation would model a flexibility that does
    not exist and make every read a join.
    """

    __tablename__ = "matches"
    __table_args__ = (
        Index("uq_match_court", "round_id", "court", unique=True),
        CheckConstraint(
            "(score_a IS NULL) = (score_b IS NULL)",
            name="ck_match_score_complete",
        ),
        CheckConstraint(
            "score_a IS NULL OR (score_a >= 0 AND score_b >= 0)",
            name="ck_match_score_non_negative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=new_id)
    round_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("rounds.id", ondelete="CASCADE"))
    court: Mapped[int] = mapped_column(Integer)

    team_a1: Mapped[uuid.UUID] = mapped_column(Uuid)
    team_a2: Mapped[uuid.UUID] = mapped_column(Uuid)
    team_b1: Mapped[uuid.UUID] = mapped_column(Uuid)
    team_b2: Mapped[uuid.UUID] = mapped_column(Uuid)

    #: Both NULL until the match is played; the check constraint keeps them in step.
    score_a: Mapped[int | None] = mapped_column(Integer, default=None)
    score_b: Mapped[int | None] = mapped_column(Integer, default=None)

    round: Mapped[Round] = relationship(lazy="raise_on_sql", back_populates="matches")

    @property
    def played(self) -> bool:
        return self.score_a is not None
