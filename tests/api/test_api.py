"""The HTTP surface, exercised end to end against a real database."""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from conftest import NAMES, seed_tournament
from padel_tour.engine import Format
from padel_tour.services import finish_tournament

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession


# --------------------------------------------------------------------------- meta


async def test_health_reports_the_database(client: AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "database": "ok"}


# --------------------------------------------------------------------------- groups


async def test_groups_are_listed_with_their_size(
    client: AsyncClient, session: AsyncSession
) -> None:
    await seed_tournament(session)

    response = await client.get("/api/groups")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "Вторничный падел"
    assert body[0]["player_count"] == 8


async def test_a_group_carries_its_roster(client: AsyncClient, session: AsyncSession) -> None:
    view = await seed_tournament(session)

    response = await client.get(f"/api/groups/{view.group_id}")
    assert response.status_code == 200
    assert {player["name"] for player in response.json()["players"]} == set(NAMES)


async def test_an_unknown_group_is_a_404(client: AsyncClient) -> None:
    response = await client.get(f"/api/groups/{uuid.uuid7()}")
    assert response.status_code == 404
    assert "no group" in response.json()["detail"]


# --------------------------------------------------------------------------- active


async def test_an_idle_group_answers_204_not_404(
    client: AsyncClient, session: AsyncSession
) -> None:
    """An empty court is not an error — the group exists, it just is not playing."""
    view = await seed_tournament(session)
    await finish_tournament(session, view.id)
    await session.commit()

    response = await client.get(f"/api/groups/{view.group_id}/active")
    assert response.status_code == 204
    assert not response.content


async def test_the_active_tournament_comes_back_whole(
    client: AsyncClient, session: AsyncSession
) -> None:
    view = await seed_tournament(session, rounds_to_play=2)

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
    client: AsyncClient, session: AsyncSession
) -> None:
    view = await seed_tournament(session, rounds_to_play=1)
    await finish_tournament(session, view.id)
    await session.commit()

    body = (await client.get(f"/api/groups/{view.group_id}/tournaments")).json()
    assert len(body) == 1
    assert body[0]["finished"] is True
    assert body[0]["winner_name"] in NAMES


async def test_the_archive_is_pageable(client: AsyncClient, session: AsyncSession) -> None:
    view = await seed_tournament(session)
    response = await client.get(
        f"/api/groups/{view.group_id}/tournaments", params={"limit": 1, "offset": 1}
    )
    assert response.status_code == 200
    assert response.json() == []


async def test_a_silly_page_size_is_rejected(client: AsyncClient, session: AsyncSession) -> None:
    view = await seed_tournament(session)
    response = await client.get(f"/api/groups/{view.group_id}/tournaments", params={"limit": 5000})
    assert response.status_code == 422


# --------------------------------------------------------------------------- players


async def test_a_player_profile_adds_up(client: AsyncClient, session: AsyncSession) -> None:
    view = await seed_tournament(session, rounds_to_play=2)
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
    client: AsyncClient, session: AsyncSession
) -> None:
    """Coming first in a tournament nobody played is not an achievement."""
    view = await seed_tournament(session)
    body = (await client.get(f"/api/players/{view.standings[0].player_id}")).json()
    assert body["matches"] == 0
    assert body["best_rank"] is None
    assert body["average_points"] == 0


async def test_an_unknown_player_is_a_404(client: AsyncClient) -> None:
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


async def test_the_schema_is_published(client: AsyncClient) -> None:
    body = (await client.get("/openapi.json")).json()
    paths = set(body["paths"])
    assert "/api/tournaments/{tournament_id}" in paths
    # The webhook is machinery, not a public endpoint.
    assert "/api/telegram/webhook" not in paths
