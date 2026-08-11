"""Every field that leaves this process, listed once, so adding one is a decision.

This exists because of the trade recorded in Р-045. Merging the wire models into the views
removed a whole class of drift, but it flipped the direction a mistake falls in. Two designs
were on the table:

*Inheritance* — a public base class, an internal subclass that adds the private fields, and
the route declaring the base. A forgotten field then simply does not ship: the failure is a
client missing data, which somebody notices within the hour. Safe direction.

*``Field(exclude=True)``* — one class, private fields marked. A forgotten field ships. If it
happens to be a secret, that is a leak, and nothing about it is loud.

We kept ``exclude``, for a reason that only showed up when it was measured: with inheritance,
``Base.model_validate(subclass_instance)`` hands back the *subclass*, unfiltered — Pydantic's
``revalidate_instances`` defaults to ``never``. Only FastAPI filters, because only FastAPI
serialises through the declared type. So any dump that is not an HTTP response — a payload
for the bot, a debug log, a queue message — would carry everything, silently. ``exclude``
holds on every path: ``model_dump``, ``model_dump_json``, nested inside another model, and
through FastAPI.

That leaves the fail-open direction to deal with, and this file is how. It is not a style
check; it is the list of what is published. Add a field to any view and this fails, naming
it, and the fix is one of two lines: add it here because clients should have it, or mark it
``exclude=True`` because they should not. Both are deliberate, which is the whole point —
the danger was never getting it wrong, it was not being asked.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

import padel_tour.api.schemas  # noqa: F401 - imported so every view class is built
from padel_tour.services import View

#: What each view publishes. Serialisation shape — the one a client actually reads.
PUBLISHED: dict[str, set[str]] = {
    "GroupView": {"id", "name", "player_count"},
    "PlayerView": {"id", "group_id", "name", "is_active"},
    "MatchView": {
        "court",
        "team_a",
        "team_b",
        "score_a",
        "score_b",
        "team_a_ids",
        "team_b_ids",
    },
    "RoundView": {"number", "matches", "complete"},
    "StandingView": {
        "rank",
        "player_id",
        "name",
        "played",
        "wins",
        "draws",
        "losses",
        "points_for",
        "points_against",
        "diff",
    },
    "ProgressPointView": {"round_no", "points_for", "cumulative_points", "rank"},
    "PlayerProgress": {"player_id", "name", "points"},
    "Viewing": {"is_member", "is_organiser", "plays_as", "anyone_may_score"},
    "TournamentView": {
        "id",
        "group_id",
        "format",
        "points_per_match",
        "pairing_pattern",
        "total_rounds",
        "finished",
        "created_at",
        "finished_at",
        "rounds",
        "standings",
        "progression",
        "rounds_played",
        "viewer",
    },
    "TournamentSummary": {
        "id",
        "format",
        "finished",
        "player_count",
        "rounds_played",
        "total_rounds",
        "created_at",
        "winner_name",
    },
    # Serialised as ``id``, not ``player_id`` — see the alias on the field.
    "PlayerStats": {
        "id",
        "name",
        "tournaments",
        "matches",
        "wins",
        "points_for",
        "average_points",
        "best_rank",
        "podiums",
        "history",
    },
}


def views() -> dict[str, type[View]]:
    """Every view there is, found rather than listed — a list would need maintaining too."""
    found: dict[str, type[View]] = {}
    pending = [View]
    while pending:
        for subclass in pending.pop().__subclasses__():
            found[subclass.__name__] = subclass
            pending.append(subclass)
    return found


def published_by(view: type[BaseModel]) -> set[str]:
    return set(view.model_json_schema(mode="serialization")["properties"])


def test_no_view_publishes_a_field_nobody_decided_on() -> None:
    """The one that catches a private field added and not excluded."""
    surprises = {
        name: published_by(view) - PUBLISHED.get(name, set())
        for name, view in views().items()
        if published_by(view) - PUBLISHED.get(name, set())
    }

    assert not surprises, (
        f"these fields are now on the wire and are not in PUBLISHED: {surprises}. "
        "Add them there if a client should have them, or mark them Field(exclude=True)."
    )


def test_nothing_a_client_reads_has_quietly_disappeared() -> None:
    """The other direction: a field excluded by accident breaks a page, not a test."""
    missing = {
        name: expected - published_by(view)
        for name, view in views().items()
        if (expected := PUBLISHED.get(name, set())) - published_by(view)
    }

    assert not missing, f"these fields stopped being published: {missing}"


def test_every_view_is_accounted_for() -> None:
    """A new view class is a new wire contract, and it should arrive as a decision too."""
    assert set(views()) == set(PUBLISHED)


def test_the_check_can_actually_see_a_field() -> None:
    """A guard nobody has watched fail is a guard nobody knows works.

    Deliberately not a ``View`` subclass: these would register in ``View.__subclasses__()``
    and the test above would then be counting them, which is a flake that only shows up when
    the suite runs in a different order.
    """

    class Leaky(BaseModel):
        id: int
        secret: str

    class Careful(BaseModel):
        id: int
        secret: str = Field(exclude=True)

    assert published_by(Leaky) == {"id", "secret"}
    assert published_by(Careful) == {"id"}
