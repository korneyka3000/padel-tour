"""Running a tournament over HTTP.

The service layer already has its own tests for the rules. These are about the transport:
that a browser can get from an empty roster to a finished tournament, that the one endpoint
which writes a score handles both the first entry and the correction, and that what a page
is told about its own permissions matches what the server will actually allow.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from conftest import NAMES, OWNER_EMAIL, sign_in
from padel_tour.services import account_for_identity, add_player, create_group

if TYPE_CHECKING:
    from collections.abc import Sequence

    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

    from padel_tour.db import Account
    from padel_tour.services.mail import InMemoryMailer

PLAYER_EMAIL = "anya@example.com"


async def owner_account(
    factory: async_sessionmaker[AsyncSession], email: str = OWNER_EMAIL
) -> Account | None:
    async with factory() as session:
        return await account_for_identity(session, "email", email)


async def make_group(
    factory: async_sessionmaker[AsyncSession],
    email: str = OWNER_EMAIL,
    *,
    names: Sequence[str] = NAMES,
) -> tuple[str, list[str]]:
    """A group owned by the signed-in account, with a roster. Returns ids as strings."""
    account = await owner_account(factory, email)
    assert account is not None
    async with factory() as session:
        group = await create_group(session, "Вторничный падел", owner_account_id=account.id)
        players = [
            str((await add_player(session, group.id, name, actor=account)).id) for name in names
        ]
        await session.commit()
        return str(group.id), players


async def draw(client: AsyncClient, group_id: str, players: list[str], **extra: object) -> dict:
    body = {"player_ids": players, "format": "americano", "points_per_match": 24, **extra}
    response = await client.post(f"/api/groups/{group_id}/tournaments", json=body)
    assert response.status_code == 201, response.text
    return response.json()


# --------------------------------------------------------------------------- drawing


async def test_a_tournament_can_be_drawn_from_the_browser(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)

    drawn = await draw(client, group_id, players)

    assert len(drawn["rounds"]) == 7
    assert drawn["group_id"] == group_id
    assert drawn["viewer"]["is_organiser"] is True


async def test_the_engine_explains_a_roster_that_does_not_fit(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    """Six people cannot play an Americano, and the refusal has to say what would work."""
    await sign_in(client, mailer)
    group_id, players = await make_group(factory, names=NAMES[:6])

    response = await client.post(
        f"/api/groups/{group_id}/tournaments",
        json={"player_ids": players, "format": "americano", "points_per_match": 24},
    )

    assert response.status_code == 400
    assert "4" in response.json()["detail"]


async def test_a_mexicano_keeps_the_round_count_and_an_americano_ignores_it(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    """One form serves both formats, so the field arrives either way."""
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)

    americano = await draw(client, group_id, players, rounds=3)
    assert americano["total_rounds"] == 7

    await client.post(f"/api/tournaments/{americano['id']}/finish")
    mexicano = await draw(client, group_id, players, format="mexicano", rounds=3)
    assert mexicano["total_rounds"] == 3


async def test_a_redraw_gives_a_whole_new_schedule(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    """Not asserting the pairs differ: a reshuffle may land on the same arrangement, rarely,
    and a test that fails once a season is worse than one that checks something solid."""
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)
    drawn = await draw(client, group_id, players)

    response = await client.post(f"/api/tournaments/{drawn['id']}/reroll")

    assert response.status_code == 200, response.text
    redrawn = response.json()
    assert len(redrawn["rounds"]) == 7
    assert all(len(rnd["matches"]) == 2 for rnd in redrawn["rounds"])
    assert not any(match["score_a"] is not None for match in redrawn["rounds"][0]["matches"])


async def test_a_redraw_after_the_first_score_is_refused(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    """Reshuffling people who have already played would erase a match that happened."""
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)
    drawn = await draw(client, group_id, players)
    await client.put(
        f"/api/tournaments/{drawn['id']}/rounds/1/courts/1", json={"score_a": 17, "score_b": 7}
    )

    response = await client.post(f"/api/tournaments/{drawn['id']}/reroll")

    assert response.status_code == 400


# --------------------------------------------------------------------------- scoring


async def test_one_endpoint_records_a_score_and_then_corrects_it(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    """A phone entering what the court now says does not know if it is the first time."""
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)
    drawn = await draw(client, group_id, players)
    where = f"/api/tournaments/{drawn['id']}/rounds/1/courts/1"

    first = await client.put(where, json={"score_a": 17, "score_b": 7})
    assert first.status_code == 200, first.text
    assert first.json()["rounds"][0]["matches"][0]["score_a"] == 17

    again = await client.put(where, json={"score_a": 13, "score_b": 11})
    assert again.status_code == 200, again.text
    assert again.json()["rounds"][0]["matches"][0]["score_a"] == 13


async def test_a_score_that_does_not_add_up_is_refused(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)
    drawn = await draw(client, group_id, players)

    response = await client.put(
        f"/api/tournaments/{drawn['id']}/rounds/1/courts/1", json={"score_a": 17, "score_b": 17}
    )

    assert response.status_code == 400
    assert "24" in response.json()["detail"]


async def test_the_standings_come_back_with_the_score(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    """The point of answering with the whole tournament: no second request to redraw."""
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)
    drawn = await draw(client, group_id, players)

    scored = await client.put(
        f"/api/tournaments/{drawn['id']}/rounds/1/courts/1", json={"score_a": 17, "score_b": 7}
    )

    assert scored.json()["standings"][0]["points_for"] == 17


# --------------------------------------------------------------------------- lifecycle


async def test_a_mexicano_draws_its_next_round_on_request(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)
    drawn = await draw(client, group_id, players, format="mexicano", rounds=3)
    assert len(drawn["rounds"]) == 1

    for match in drawn["rounds"][0]["matches"]:
        await client.put(
            f"/api/tournaments/{drawn['id']}/rounds/1/courts/{match['court']}",
            json={"score_a": 14, "score_b": 10},
        )

    response = await client.post(f"/api/tournaments/{drawn['id']}/next-round")

    assert response.status_code == 200, response.text
    assert len(response.json()["rounds"]) == 2


async def test_finishing_early_keeps_the_table(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)
    drawn = await draw(client, group_id, players)
    await client.put(
        f"/api/tournaments/{drawn['id']}/rounds/1/courts/1", json={"score_a": 17, "score_b": 7}
    )

    response = await client.post(f"/api/tournaments/{drawn['id']}/finish")

    assert response.status_code == 200, response.text
    assert response.json()["finished"] is True
    assert response.json()["standings"][0]["points_for"] == 17


# --------------------------------------------------------------------------- who may


async def test_a_stranger_is_told_they_may_do_nothing(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    """The page is open by link; the buttons on it are not."""
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)
    drawn = await draw(client, group_id, players)
    await client.post("/api/auth/sign-out")

    response = await client.get(f"/api/tournaments/{drawn['id']}")

    assert response.status_code == 200
    assert response.json()["viewer"] == {
        "is_member": False,
        "is_organiser": False,
        "plays_as": None,
        "anyone_may_score": False,
    }


async def test_a_stranger_cannot_write_a_score(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)
    drawn = await draw(client, group_id, players)
    await client.post("/api/auth/sign-out")

    response = await client.put(
        f"/api/tournaments/{drawn['id']}/rounds/1/courts/1", json={"score_a": 17, "score_b": 7}
    )

    assert response.status_code == 401


async def test_the_matches_carry_ids_so_a_page_can_tell_which_court_is_yours(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    """Names cannot answer this: two people in a group may share one."""
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)

    drawn = await draw(client, group_id, players)

    match = drawn["rounds"][0]["matches"][0]
    on_court = set(match["team_a_ids"] + match["team_b_ids"])
    assert len(on_court) == 4
    assert on_court <= set(players)


# --------------------------------------------------------------------------- roster


async def test_a_player_can_be_renamed(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    await sign_in(client, mailer)
    _, players = await make_group(factory)

    response = await client.patch(f"/api/players/{players[0]}", json={"name": "Анна"})

    assert response.status_code == 200, response.text
    assert response.json()["name"] == "Анна"


async def test_removing_a_player_hides_them_rather_than_deleting_them(
    client: AsyncClient, mailer: InMemoryMailer, factory: async_sessionmaker[AsyncSession]
) -> None:
    """Their past matches are the group's history, and history does not get rewritten."""
    await sign_in(client, mailer)
    group_id, players = await make_group(factory)

    response = await client.delete(f"/api/players/{players[0]}")

    assert response.status_code == 204
    roster = (await client.get(f"/api/groups/{group_id}")).json()["players"]
    assert players[0] not in [player["id"] for player in roster]
    assert len(roster) == len(players) - 1


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("patch", "/api/players/{player}", {"name": "Анна"}),
        ("delete", "/api/players/{player}", None),
    ],
)
async def test_editing_the_roster_needs_an_account(
    client: AsyncClient,
    mailer: InMemoryMailer,
    factory: async_sessionmaker[AsyncSession],
    method: str,
    path: str,
    body: dict | None,
) -> None:
    await sign_in(client, mailer)
    _, players = await make_group(factory)
    await client.post("/api/auth/sign-out")

    call = getattr(client, method)
    response = await (
        call(path.format(player=players[0]), json=body)
        if body is not None
        else call(path.format(player=players[0]))
    )

    assert response.status_code == 401
