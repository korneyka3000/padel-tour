"""The administrator's endpoints, and the two things about them that must never slip.

**Shut by default.** The first test walks the OpenAPI document and demands a refusal from
every ``/api/admin`` path there is, rather than from a list somebody maintains. A route added
next month without its dependency fails here, named, instead of being open and quiet — which
is the only failure mode of an admin API that nobody notices.

**Nothing secret leaves.** The table browser will show any table in the schema, including
``sessions`` and ``magic_links``. Those hold hashes rather than tokens, so one would grant
nothing, but a screen that prints secret-shaped values teaches a habit, and the redaction is
by column name across every table so a new table with the same column is covered on arrival.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlalchemy import select

from conftest import OWNER_EMAIL, seed_tournament, sign_in
from padel_tour.api.app import create_app
from padel_tour.db import PROVIDER_EMAIL, PROVIDER_TELEGRAM, LoginSession
from padel_tour.services import (
    account_for_identity,
    account_for_session,
    claim_player,
    create_group,
    ensure_identity,
    open_session,
)

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account
    from padel_tour.services.mail import InMemoryMailer

#: Every admin route, as (method, path-with-holes), read from the app rather than listed.
ADMIN_ROUTES = sorted(
    (method.upper(), path)
    for path, operations in create_app().openapi()["paths"].items()
    if path.startswith("/api/admin")
    for method in operations
)

#: A value for every path parameter. Any well-formed one will do — these tests are about
#: being refused, and a refusal must come before the row is looked for.
FILLER = "00000000-0000-4000-8000-000000000000"


def concrete(path: str) -> str:
    """A path with every hole filled, so the refusal is the only thing being measured."""
    for hole in ("{group_id}", "{player_id}", "{tournament_id}"):
        path = path.replace(hole, FILLER)
    return path.replace("{name}", "accounts")


async def become_admin(
    client: AsyncClient, mailer: InMemoryMailer, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ADMIN_EMAILS", OWNER_EMAIL)
    await sign_in(client, mailer)


# ------------------------------------------------------------------------- shut by default


def test_there_are_admin_routes_to_check() -> None:
    """A discovery bug here would make every test below pass by finding nothing."""
    assert len(ADMIN_ROUTES) > 8


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES, ids=str)
async def test_a_stranger_is_refused(client: AsyncClient, method: str, path: str) -> None:
    response = await client.request(method, concrete(path))

    assert response.status_code == 401, f"{method} {path} answered a signed-out caller"


@pytest.mark.parametrize(("method", "path"), ADMIN_ROUTES, ids=str)
async def test_an_ordinary_account_is_refused(
    client: AsyncClient,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    path: str,
) -> None:
    """Signed in is not the same as allowed, and 403 says which of the two is missing."""
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    monkeypatch.delenv("ADMIN_TELEGRAM_IDS", raising=False)
    await sign_in(client, mailer)

    response = await client.request(method, concrete(path))

    assert response.status_code == 403, f"{method} {path} answered an ordinary account"


# -------------------------------------------------------------------------------- reading


async def test_the_overview_counts_what_is_there(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await seed_tournament(session)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    body = (await client.get("/api/admin/totals")).json()

    assert body["groups"] == 1
    assert body["players"] == 8
    assert body["tournaments"] == 1
    assert body["accounts"] >= 1


async def test_accounts_carry_the_ways_in(
    client: AsyncClient, mailer: InMemoryMailer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Most accounts have no display name, so the identity is the only way to tell who."""
    await become_admin(client, mailer, monkeypatch)

    body = (await client.get("/api/admin/accounts")).json()

    ways = [
        (entry["provider"], entry["external_id"]) for row in body for entry in row["identities"]
    ]
    assert (PROVIDER_EMAIL, OWNER_EMAIL) in ways


async def test_an_admin_sees_a_group_they_are_not_in(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other = await ensure_identity(session, PROVIDER_EMAIL, "elsewhere@example.com")
    await create_group(session, "Чужая группа", owner_account_id=other.id)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    names = [row["name"] for row in (await client.get("/api/admin/groups")).json()]

    assert "Чужая группа" in names


# ------------------------------------------------------------------------- the table browser


async def test_the_browser_lists_every_table(
    client: AsyncClient, mailer: InMemoryMailer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Read off the metadata, so a table added by a migration appears without being listed."""
    await become_admin(client, mailer, monkeypatch)

    names = {row["name"] for row in (await client.get("/api/admin/tables")).json()}

    assert {"accounts", "groups", "players", "tournaments", "sessions"} <= names


async def test_a_page_shows_what_is_stored(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    await seed_tournament(session)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    body = (await client.get("/api/admin/tables/players")).json()

    assert body["total"] == 8
    assert "name" in body["columns"]
    assert len(body["rows"]) == 8


async def test_a_token_hash_never_leaves(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Signing in created a session row, so there is a real hash to withhold.

    Checked against the stored value rather than the word: the column name appears in
    ``redacted`` on purpose, so that its absence from the rows is stated rather than
    mysterious, and asserting on the word would only have caught that.
    """
    await become_admin(client, mailer, monkeypatch)
    stored = await session.scalar(select(LoginSession.token_hash))
    assert stored, "no session row, so this test proved nothing"

    response = await client.get("/api/admin/tables/sessions")
    body = response.json()

    assert stored not in response.text
    assert "token_hash" not in body["columns"]
    assert all("token_hash" not in row for row in body["rows"])
    assert body["redacted"] == ["token_hash"]


@pytest.mark.parametrize("table", ["sessions", "magic_links", "invites"])
async def test_every_table_holding_a_hash_withholds_it(
    client: AsyncClient,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
    table: str,
) -> None:
    """By column name across the schema, so a new table with one is covered on arrival."""
    await become_admin(client, mailer, monkeypatch)

    body = (await client.get(f"/api/admin/tables/{table}")).json()

    assert "token_hash" not in body["columns"]


async def test_an_unknown_table_is_404_not_a_crash(
    client: AsyncClient, mailer: InMemoryMailer, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The name comes from a URL, so it is a stranger's string until proven otherwise."""
    await become_admin(client, mailer, monkeypatch)

    assert (await client.get("/api/admin/tables/pg_user")).status_code == 404


# -------------------------------------------------------------------------------- writing


async def test_deleting_a_group_says_what_it_took(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The cascade is the whole danger, so the count is part of the answer."""
    view = await seed_tournament(session, rounds_to_play=1)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    preview = (await client.get(f"/api/admin/groups/{view.group_id}/impact")).json()
    response = await client.delete(f"/api/admin/groups/{view.group_id}")

    assert preview == {"name": "Вторничный падел", "players": 8, "tournaments": 1}
    assert response.json() == preview
    assert (await client.get(f"/api/tournaments/{view.id}")).status_code == 404


async def test_deleting_a_tournament_leaves_its_group(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    view = await seed_tournament(session, rounds_to_play=1)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    assert (await client.delete(f"/api/admin/tournaments/{view.id}")).status_code == 204
    assert (await client.get(f"/api/tournaments/{view.id}")).status_code == 404
    assert {row["id"] for row in (await client.get("/api/admin/groups")).json()} == {
        str(view.group_id)
    }


async def test_a_player_can_be_attached_and_let_go(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The point of the people screen: bind a roster name to a person who is not you."""
    view = await seed_tournament(session)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)
    me = await account_for_identity(session, PROVIDER_EMAIL, OWNER_EMAIL)
    assert me is not None
    player_id = view.standings[0].player_id

    attached = await client.post(
        f"/api/admin/players/{player_id}/attach", json={"account_id": str(me.id)}
    )
    claimed = (await client.get(f"/api/groups/{view.group_id}")).json()["players"]

    assert attached.status_code == 204
    assert any(row["id"] == str(player_id) and row["is_claimed"] for row in claimed)

    assert (await client.post(f"/api/admin/players/{player_id}/detach")).status_code == 204
    released = (await client.get(f"/api/groups/{view.group_id}")).json()["players"]
    assert not any(row["id"] == str(player_id) and row["is_claimed"] for row in released)


async def test_detaching_a_player_nobody_holds_is_not_an_error(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The caller asked for the player to be unheld, and they are."""
    view = await seed_tournament(session)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    response = await client.post(f"/api/admin/players/{view.standings[0].player_id}/detach")

    assert response.status_code == 204


async def test_a_group_can_be_handed_to_nobody(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Not a clearing: no owner is the shape a chat makes, and it opens the group to members.

    This is how one stuck behind a departed owner gets unstuck.
    """
    other = await ensure_identity(session, PROVIDER_EMAIL, "gone@example.com")
    group = await create_group(session, "Осиротевшая", owner_account_id=other.id)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    response = await client.put(f"/api/admin/groups/{group.id}/owner", json={"account_id": None})

    assert response.status_code == 204
    assert (await client.get(f"/api/groups/{group.id}")).json()["is_owner"] is True


# ---------------------------------------------------------------------------------- merging
#
# One person, two accounts. The doors mint different ones — a magic link resolves by address,
# a bot link by account — so somebody who used both appears twice with their history split
# down the middle. Merging is how it gets put back, and the interesting part is what it
# refuses to do.


async def two_of_me(session: AsyncSession) -> tuple[Account, Account]:
    by_mail = await ensure_identity(session, PROVIDER_EMAIL, "same.person@example.com")
    by_chat = await ensure_identity(session, PROVIDER_TELEGRAM, "424242")
    return by_mail, by_chat


async def test_merging_moves_everything_and_removes_the_spare(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    by_mail, by_chat = await two_of_me(session)
    view = await seed_tournament(session, owner=by_chat)
    # Whoever the tie-break puts first in an unplayed tournament — the name is not the point,
    # only that the same one comes out the other side.
    mine = view.standings[0]
    await claim_player(session, mine.player_id, by_chat)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    response = await client.post(
        f"/api/admin/accounts/{by_chat.id}/merge", json={"into": str(by_mail.id)}
    )
    body = response.json()

    assert response.status_code == 200
    assert body["possible"] is True
    # Everything it was: the group it owned, the tournament it organised, the player it
    # held, and the way it signed in.
    assert body["moving"] == {
        "groups": 1,
        "tournaments": 1,
        "players": 1,
        "identities": 1,
    }
    assert [one["provider"] for one in body["gaining"]] == [PROVIDER_TELEGRAM]

    left = (await client.get("/api/admin/accounts")).json()
    assert str(by_chat.id) not in [row["id"] for row in left]
    survivor = next(row for row in left if row["id"] == str(by_mail.id))
    assert {one["provider"] for one in survivor["identities"]} == {
        PROVIDER_EMAIL,
        PROVIDER_TELEGRAM,
    }
    assert [one["name"] for one in survivor["players"]] == [mine.name]


async def test_the_preview_says_the_same_thing_beforehand(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The confirmation and the receipt cannot be allowed to disagree."""
    by_mail, by_chat = await two_of_me(session)
    view = await seed_tournament(session, owner=by_chat)
    await claim_player(session, view.standings[0].player_id, by_chat)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    preview = await client.get(
        f"/api/admin/accounts/{by_chat.id}/merge-preview", params={"into": str(by_mail.id)}
    )
    done = await client.post(
        f"/api/admin/accounts/{by_chat.id}/merge", json={"into": str(by_mail.id)}
    )

    assert preview.json() == done.json()


async def test_two_email_accounts_refuse_to_merge(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One account holds at most one login per provider, so this needs a decision.

    Which address to keep is not something a rule can answer, and guessing would silently
    throw one away.
    """
    one = await ensure_identity(session, PROVIDER_EMAIL, "first@example.com")
    two = await ensure_identity(session, PROVIDER_EMAIL, "second@example.com")
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    preview = await client.get(
        f"/api/admin/accounts/{one.id}/merge-preview", params={"into": str(two.id)}
    )
    attempt = await client.post(f"/api/admin/accounts/{one.id}/merge", json={"into": str(two.id)})

    assert preview.json()["possible"] is False
    assert preview.json()["conflicts"] == ["both sign in by email"]
    assert attempt.status_code == 409
    assert len((await client.get("/api/admin/accounts")).json()) >= 2


async def test_holding_two_players_in_one_group_refuses_to_merge(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Merging would assert that two people on one roster are the same person.

    Answered by detaching the wrong one, which is a decision, not a rule.
    """
    by_mail, by_chat = await two_of_me(session)
    view = await seed_tournament(session, owner=by_chat)
    await claim_player(session, view.standings[0].player_id, by_chat)
    await claim_player(session, view.standings[1].player_id, by_mail)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    preview = await client.get(
        f"/api/admin/accounts/{by_chat.id}/merge-preview", params={"into": str(by_mail.id)}
    )

    assert preview.json()["possible"] is False
    assert preview.json()["conflicts"] == ["both hold a player in Вторничный падел"]


async def test_an_account_cannot_be_merged_into_itself(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """It would delete the survivor. Refused before anything is counted."""
    by_mail, _ = await two_of_me(session)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    attempt = await client.post(
        f"/api/admin/accounts/{by_mail.id}/merge", json={"into": str(by_mail.id)}
    )

    assert attempt.status_code == 403


async def test_the_merged_account_is_signed_out_rather_than_carried_over(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A live session names a way in, and moving one is handing over a door.

    The person signs in again — through either identity, both of which now reach the same
    account, which is the entire point of having merged them.
    """
    by_mail, by_chat = await two_of_me(session)
    token = await open_session(session, by_chat)
    await session.commit()
    await become_admin(client, mailer, monkeypatch)

    await client.post(f"/api/admin/accounts/{by_chat.id}/merge", json={"into": str(by_mail.id)})

    assert await account_for_session(session, token) is None
