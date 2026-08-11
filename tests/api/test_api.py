"""The HTTP surface, exercised end to end against a real database."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from conftest import NAMES, seed_tournament, sign_in
from padel_tour.api import routes
from padel_tour.db import PROVIDER_EMAIL
from padel_tour.engine import Format
from padel_tour.services import account_for_identity, finish_tournament

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

    from padel_tour.db import Account
    from padel_tour.services import TournamentView
    from padel_tour.services.mail import InMemoryMailer


async def owner_account(session: AsyncSession, address: str) -> Account:
    """The account a sign-in just created, from the other side of the transaction."""
    account = await account_for_identity(session, PROVIDER_EMAIL, address)
    assert account is not None
    return account


async def mine(
    client: AsyncClient,
    session: AsyncSession,
    mailer: InMemoryMailer,
    *,
    rounds_to_play: int = 0,
) -> TournamentView:
    """Sign in, then seed a group this account owns.

    Everything group-scoped is now private to its members, so a test that reads a roster,
    an archive or a profile has to be somebody first.
    """
    address = await sign_in(client, mailer)
    view = await seed_tournament(
        session, rounds_to_play=rounds_to_play, owner=await owner_account(session, address)
    )
    await session.commit()
    return view


# --------------------------------------------------------------------------- meta


async def test_health_reports_the_database(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


@pytest.mark.parametrize(
    ("table", "column"),
    [
        ("tournaments", "chart_message_id"),
        # The second incident was this one, while the check was watching tournaments.
        ("magic_links", "account_id"),
    ],
)
async def test_health_notices_a_schema_that_has_fallen_behind_the_code(
    client: AsyncClient, engine: AsyncEngine, table: str, column: str
) -> None:
    """The case this endpoint exists for, and the one it twice failed to catch.

    A deploy landing before its migration leaves the code believing in a column the database
    has not got. Connectivity is perfect throughout, so the service reports healthy while
    half the API answers 500 (Р-039, Р-043). Any mapped table, not a sampled one — the
    second time round it was the table nobody had thought to sample.
    """
    async with engine.begin() as connection:
        await connection.execute(text(f"ALTER TABLE {table} DROP COLUMN {column}"))

    response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert f"{table}.{column}" in body["database"]


# --------------------------------------------------------------------------- groups


async def test_your_groups_are_listed_with_their_size(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    await mine(client, session, mailer)

    response = await client.get("/api/groups")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Вторничный падел"
    assert body[0]["player_count"] == 8


async def test_a_group_carries_its_roster(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    view = await mine(client, session, mailer)

    response = await client.get(f"/api/groups/{view.group_id}")
    assert response.status_code == 200
    assert {player["name"] for player in response.json()["players"]} == set(NAMES)


async def test_an_unknown_group_is_a_404(client: AsyncClient, mailer: InMemoryMailer) -> None:
    await sign_in(client, mailer)
    response = await client.get(f"/api/groups/{uuid.uuid7()}")
    assert response.status_code == 404
    assert "no group" in response.json()["detail"]


# --------------------------------------------------------------------------- active


async def test_an_idle_group_answers_204_not_404(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    """An empty court is not an error — the group exists, it just is not playing."""
    view = await mine(client, session, mailer)
    await finish_tournament(session, view.id)
    await session.commit()

    response = await client.get(f"/api/groups/{view.group_id}/active")
    assert response.status_code == 204
    assert not response.content


async def test_the_active_tournament_comes_back_whole(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    view = await mine(client, session, mailer, rounds_to_play=2)

    response = await client.get(f"/api/groups/{view.group_id}/active")
    assert response.status_code == 200

    body = response.json()
    assert body["id"] == str(view.id)
    assert body["format"] == Format.AMERICANO.value
    assert body["total_rounds"] == 7
    assert body["rounds_played"] == 2
    assert len(body["rounds"]) == 7
    assert len(body["standings"]) == 8


# --------------------------------------------------------------------------- tournament


async def test_a_tournament_carries_names_never_ids(
    client: AsyncClient, session: AsyncSession
) -> None:
    view = await seed_tournament(session, rounds_to_play=1)

    body = (await client.get(f"/api/tournaments/{view.id}")).json()
    first = body["rounds"][0]["matches"][0]
    assert set(first["team_a"]) <= set(NAMES)
    assert {row["name"] for row in body["standings"]} == set(NAMES)


async def test_progression_lines_match_the_standings(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The chart's legend and the table have to agree, so the API orders them the same."""
    view = await seed_tournament(session, rounds_to_play=3)

    body = (await client.get(f"/api/tournaments/{view.id}")).json()
    table_order = [row["name"] for row in body["standings"]]
    chart_order = [line["name"] for line in body["progression"]]
    assert table_order == chart_order

    for line in body["progression"]:
        assert [point["round_no"] for point in line["points"]] == [1, 2, 3]

    leader = body["progression"][0]
    assert leader["points"][-1]["cumulative_points"] == body["standings"][0]["points_for"]


async def test_an_unplayed_tournament_has_empty_progression(
    client: AsyncClient, session: AsyncSession
) -> None:
    view = await seed_tournament(session)
    body = (await client.get(f"/api/tournaments/{view.id}")).json()
    assert all(line["points"] == [] for line in body["progression"])


async def test_unfinished_matches_have_no_score(client: AsyncClient, session: AsyncSession) -> None:
    view = await seed_tournament(session)
    body = (await client.get(f"/api/tournaments/{view.id}")).json()
    match = body["rounds"][0]["matches"][0]
    assert match["score_a"] is None
    assert match["score_b"] is None
    assert body["rounds"][0]["complete"] is False


async def test_an_unknown_tournament_is_a_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/tournaments/{uuid.uuid7()}")
    assert response.status_code == 404


# --------------------------------------------------------------------------- archive


async def test_the_archive_lists_finished_tournaments(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    view = await mine(client, session, mailer, rounds_to_play=1)
    await finish_tournament(session, view.id)
    await session.commit()

    body = (await client.get(f"/api/groups/{view.group_id}/tournaments")).json()
    assert len(body) == 1
    assert body[0]["finished"] is True
    assert body[0]["winner_name"] in NAMES


async def test_the_archive_is_pageable(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    view = await mine(client, session, mailer)
    response = await client.get(
        f"/api/groups/{view.group_id}/tournaments", params={"limit": 1, "offset": 1}
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_a_silly_page_size_is_rejected(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    view = await mine(client, session, mailer)
    response = await client.get(f"/api/groups/{view.group_id}/tournaments", params={"limit": 5000})
    assert response.status_code == 422


# --------------------------------------------------------------------------- players


async def test_a_player_profile_adds_up(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    view = await mine(client, session, mailer, rounds_to_play=2)
    leader = view.standings[0]

    body = (await client.get(f"/api/players/{leader.player_id}")).json()
    assert body["name"] == leader.name
    assert body["tournaments"] == 1
    assert body["matches"] == 2
    assert body["points_for"] == leader.points_for
    assert body["average_points"] == round(leader.points_for / 2, 1)
    assert body["best_rank"] == leader.rank
    assert len(body["history"]) == 1


async def test_a_player_who_has_not_played_has_no_rank(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    """Coming first in a tournament nobody played is not an achievement."""
    view = await mine(client, session, mailer)
    body = (await client.get(f"/api/players/{view.standings[0].player_id}")).json()
    assert body["matches"] == 0
    assert body["best_rank"] is None
    assert body["average_points"] == 0


async def test_an_unknown_player_is_a_404(client: AsyncClient, mailer: InMemoryMailer) -> None:
    await sign_in(client, mailer)
    assert (await client.get(f"/api/players/{uuid.uuid7()}")).status_code == 404


# --------------------------------------------------------------------------- shape


async def test_the_api_never_leaks_engine_internals(
    client: AsyncClient, session: AsyncSession
) -> None:
    """``TournamentView`` carries a whole engine state; none of it belongs on the wire."""
    view = await seed_tournament(session, rounds_to_play=1)
    body = (await client.get(f"/api/tournaments/{view.id}")).json()
    assert "state" not in body
    assert "seed" not in body


async def test_the_schema_and_docs_live_under_the_api_prefix(client: AsyncClient) -> None:
    """Anything outside /api is rewritten to the web app in production.

    At their default paths the docs answered 200 with a React page: reachable, wrong, and
    quiet about it. These assertions are the only thing standing between us and that.
    """
    for path in ("/api/docs", "/api/redoc"):
        assert (await client.get(path)).status_code == 200, path
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert (await client.get(path)).status_code == 404, path

    body = (await client.get("/api/openapi.json")).json()
    paths = set(body["paths"])
    assert "/api/tournaments/{tournament_id}" in paths
    # The webhook is machinery, not a public endpoint.
    assert "/api/telegram/webhook" not in paths


async def test_health_stops_looking_once_the_schema_matches(client: AsyncClient) -> None:
    """A catalogue scan on every uptime ping is a cost with no buyer.

    The schema cannot move under a running process without a migration, and on this
    deployment a migration means a new process — so a match is remembered. The second call
    is a bare liveness check.
    """
    assert (await client.get("/api/health")).json()["status"] == "ok"
    assert routes._schema_verified

    assert (await client.get("/api/health")).json()["status"] == "ok"


async def test_health_keeps_looking_while_the_schema_is_behind(
    client: AsyncClient, engine: AsyncEngine
) -> None:
    """A mismatch is not remembered, so the answer flips the moment the migration lands
    rather than staying wrong until somebody restarts the thing."""
    async with engine.begin() as connection:
        await connection.execute(text("ALTER TABLE tournaments DROP COLUMN chart_message_id"))
    assert (await client.get("/api/health")).json()["status"] == "degraded"

    async with engine.begin() as connection:
        await connection.execute(text("ALTER TABLE tournaments ADD COLUMN chart_message_id BIGINT"))

    assert (await client.get("/api/health")).json()["status"] == "ok"


async def test_the_owner_account_never_reaches_a_client(
    client: AsyncClient, mailer: InMemoryMailer
) -> None:
    """One model serves the service layer and the wire, so the field it must not publish is
    excluded rather than dropped by a copy. This is the check that the exclusion holds where
    it counts: in the document clients read, and in an actual response body."""
    document = (await client.get("/api/openapi.json")).json()
    published = document["components"]["schemas"]["GroupView"]["properties"]
    assert "owner_account_id" not in published

    await sign_in(client, mailer)
    made = await client.post("/api/groups", json={"name": "Вторничный падел"})

    assert made.status_code == 201
    assert "owner_account_id" not in made.json()
