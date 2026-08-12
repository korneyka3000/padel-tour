"""One schema per thing, and the fields inside them that must never reach a client.

The views *are* the wire format — there is no second set of models in ``api/schemas`` any
more, and no mappers copying one into the other. What used to be "leave that field out of
the response model" is now ``Field(exclude=True)`` on the view itself.

That trade is worth stating, because it moves where the mistakes can happen. Before, a field
added to a view and forgotten on the wire model simply never shipped: invisible, and usually
harmless. Now a field added to a view ships by default, and forgetting to exclude a *secret*
is a leak. The upside is that the two can no longer disagree about anything else; the price
is that this file has to be thorough.

``exclude`` is a *serialisation* setting, so the guarantee is exactly as strong as the tests
below and no stronger. That is why they check the ways a value actually leaves this process,
rather than checking the field's configuration.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from padel_tour.engine import Format, PairingPattern, TournamentConfig, create_americano
from padel_tour.services import (
    GroupView,
    PlayerStats,
    TournamentSummary,
    TournamentView,
    Viewing,
)

OWNER = uuid.uuid4()
PLAYER = uuid.uuid4()


def group() -> GroupView:
    return GroupView(
        id=uuid.uuid4(), name="Вторничный падел", owner_account_id=OWNER, player_count=8
    )


def test_the_owner_is_readable_in_process() -> None:
    """Which is the whole reason the field is on the model rather than dropped."""
    assert group().owner_account_id == OWNER


def test_the_owner_does_not_survive_serialisation() -> None:
    assert "owner_account_id" not in group().model_dump()


def test_the_owner_does_not_survive_json() -> None:
    """The route FastAPI actually takes."""
    assert "owner_account_id" not in group().model_dump_json()
    assert str(OWNER) not in group().model_dump_json()


def test_the_owner_is_absent_from_the_schema_clients_read() -> None:
    """Two schemas, and only one of them is the answer.

    ``model_json_schema()`` defaults to the *validation* shape, which keeps excluded fields
    because they can still be passed in. What a client reads is the *serialisation* shape,
    which is what FastAPI puts in the OpenAPI document for a response — and the first
    version of this test asserted against the wrong one and failed, which is the only reason
    the difference is written down here.
    """
    published = GroupView.model_json_schema(mode="serialization")["properties"]

    assert "owner_account_id" not in published
    assert "owner_account_id" in GroupView.model_json_schema(mode="validation")["properties"]


def test_everything_a_client_needs_is_still_there() -> None:
    """The counterpart: excluding one field must not quietly exclude the rest."""
    assert set(group().model_dump()) == {"id", "name", "player_count"}


# ------------------------------------------------------------------- the whole tournament
#
# A tournament view carries two things a client must not have: the account id of whoever
# organises it, and the engine's own state object. The second is not a secret so much as an
# object with no business being JSON at all — it is the full draw, the seed and every result,
# reachable from a page anyone with the link can open.


def tournament(**over: object) -> TournamentView:
    """A one-round, four-player tournament — the smallest thing the engine will build."""
    state = create_americano(
        [str(uuid.uuid4()) for _ in range(4)], TournamentConfig(format=Format.AMERICANO), seed=1
    )
    fields: dict[str, object] = {
        "id": uuid.uuid4(),
        "group_id": uuid.uuid4(),
        "format": Format.AMERICANO,
        "points_per_match": 24,
        "pairing_pattern": PairingPattern.CROSSOVER,
        "total_rounds": 3,
        "finished": False,
        "created_at": datetime(2026, 8, 11, tzinfo=UTC),
        "finished_at": None,
        "organiser_account_id": OWNER,
        "rounds": (),
        "standings": (),
        "progression": (),
        "state": state,
    }
    return TournamentView.model_validate(fields | over)


def test_the_organiser_is_readable_in_process() -> None:
    """The permission check reads it on every scoring attempt."""
    assert tournament().organiser_account_id == OWNER


def test_neither_internal_field_survives_json() -> None:
    published = tournament().model_dump_json()

    assert "organiser_account_id" not in published
    assert str(OWNER) not in published
    assert "state" not in published
    assert "seed" not in published


def test_the_schema_clients_read_names_neither() -> None:
    published = TournamentView.model_json_schema(mode="serialization")["properties"]

    assert "organiser_account_id" not in published
    assert "state" not in published


def test_the_engine_state_is_not_copied() -> None:
    """``InstanceOf``, not a nested model.

    Pydantic will happily validate a dataclass by rebuilding it, field by field, all the way
    down — here that is every round, every match and every result, on a request that only
    wanted to read the standings. This pins the cheap path: the same object goes in and out.
    """
    state = create_americano(
        [str(uuid.uuid4()) for _ in range(4)], TournamentConfig(format=Format.AMERICANO), seed=1
    )

    assert tournament(state=state).state is state


def test_a_viewer_is_a_copy_not_a_mutation() -> None:
    """Who is asking belongs to the request, not to the tournament.

    Two people reading the same tournament at once must not be able to see each other's
    permissions, which is exactly what setting the field in place would allow.
    """
    view = tournament()

    mine = view.seen_by(Viewing(is_member=True, is_organiser=True))

    assert mine.viewer.is_organiser is True
    assert view.viewer.is_organiser is False


def test_a_stranger_is_the_default() -> None:
    """A link-holder gets a page with no controls, without anyone having to say so."""
    assert tournament().viewer == Viewing()


# --------------------------------------------------------------------------- the archive


def test_an_archive_line_keeps_its_extras_off_the_wire() -> None:
    """``placings`` and ``group_id`` are for the bot and the router, not for the response.

    Not secrets — the bot shows every placing to the group it belongs to. They are excluded
    because the web's archive has no room for them yet, and shipping a field no client reads
    is how a response grows to twice the size nobody asked for.
    """
    summary = TournamentSummary(
        id=uuid.uuid4(),
        group_id=uuid.uuid4(),
        format=Format.AMERICANO,
        finished=True,
        player_count=4,
        rounds_played=3,
        total_rounds=3,
        created_at=datetime(2026, 8, 11, tzinfo=UTC),
        finished_at=datetime(2026, 8, 11, tzinfo=UTC),
        winner_name="Аня",
        placings=("Аня", "Боря", "Вика", "Гриша"),
    )

    assert summary.placings[0] == "Аня"
    assert set(summary.model_dump()) == {
        "id",
        "format",
        "finished",
        "player_count",
        "rounds_played",
        "total_rounds",
        "created_at",
        "winner_name",
        # Published, and null unless the list spans groups or is about one person.
        "group_name",
        "my_rank",
    }


# ---------------------------------------------------------------------------- the profile


def profile() -> PlayerStats:
    return PlayerStats(
        player_id=PLAYER,
        name="Аня",
        tournaments=3,
        matches=21,
        wins=14,
        draws=1,
        losses=6,
        points_for=280,
        points_against=224,
        best_rank=1,
        podiums=2,
        history=(),
    )


def test_the_profile_answers_id_not_player_id() -> None:
    """A rename would break a page that reads it, and the model would still be right.

    The service says ``player_id`` because in process "which id" is a real question; the
    endpoint has always said ``id``. One ``serialization_alias`` holds both, where there used
    to be a whole class whose only difference from this one was that word.
    """
    published = profile().model_dump(by_alias=True)

    assert published["id"] == PLAYER
    assert "player_id" not in published


def test_counted_but_unshown_numbers_stay_off_the_wire() -> None:
    """Shipped on the chance a screen might want them is how a response doubles in size."""
    published = profile().model_dump(by_alias=True)

    assert profile().losses == 6
    assert {"draws", "losses", "points_against"}.isdisjoint(published)


def test_points_per_match_is_computed_and_published() -> None:
    """A derived number, and the only fair comparison when people play different amounts."""
    published = profile().model_dump(by_alias=True)

    assert published["average_points"] == 13.3
