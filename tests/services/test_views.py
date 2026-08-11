"""One schema for a group, and the field inside it that must never reach a client.

``owner_account_id`` is an account id. No client has any use for it, and knowing which
account owns a group is not something membership should buy. It lives on the model anyway,
because the alternative — a second near-identical class whose only job is to drop one field
— is a duplicate with a standing invitation to drift.

``exclude`` is a *serialisation* setting, so the guarantee is exactly as strong as the tests
below and no stronger. That is why they check the ways a value actually leaves this process,
rather than checking the field's configuration.
"""

from __future__ import annotations

import uuid

from padel_tour.services import GroupView

OWNER = uuid.uuid4()


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
