"""Your own history, across every group you play in.

A group's archive answers what the *group* has played. Somebody in two groups had no way to
see their own record in one place; they opened each group and read past everybody else.

The list is reached through the players an account has claimed, which is the only link an
account has to a tournament at all. That has a consequence worth pinning: somebody who has
been added to a roster but never claimed has played nothing, as far as this can tell. It is
correct — the name on the roster belongs to nobody yet — and it is exactly what an
invitation fixes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import OWNER_EMAIL, seed_tournament, sign_in
from padel_tour.db import PROVIDER_EMAIL
from padel_tour.services import account_for_identity, claim_player

if TYPE_CHECKING:
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account
    from padel_tour.services.mail import InMemoryMailer


async def signed_in(session: AsyncSession) -> Account:
    account = await account_for_identity(session, PROVIDER_EMAIL, OWNER_EMAIL)
    assert account is not None
    return account


async def test_signing_in_is_required(client: AsyncClient) -> None:
    """The list is defined by who is asking, so there is no anonymous version of it."""
    assert (await client.get("/api/me/tournaments")).status_code == 401


async def test_a_roster_name_you_have_not_claimed_is_not_you(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    """The owner typed eight names. None of them is an account until somebody claims one."""
    await sign_in(client, mailer)
    await seed_tournament(session, rounds_to_play=1, owner=await signed_in(session))
    await session.commit()

    assert (await client.get("/api/me/tournaments")).json() == []


async def test_claiming_a_player_makes_their_tournaments_yours(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    await sign_in(client, mailer)
    me = await signed_in(session)
    view = await seed_tournament(session, rounds_to_play=7, owner=me)
    await claim_player(session, view.standings[0].player_id, me)
    await session.commit()

    body = (await client.get("/api/me/tournaments")).json()

    assert [entry["id"] for entry in body] == [str(view.id)]


async def test_it_says_where_you_came_and_which_group(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    """Both exist for the same reason: across groups, a date and a format identify nothing."""
    await sign_in(client, mailer)
    me = await signed_in(session)
    view = await seed_tournament(session, rounds_to_play=7, owner=me)
    winner = view.standings[0]
    await claim_player(session, winner.player_id, me)
    await session.commit()

    entry = (await client.get("/api/me/tournaments")).json()[0]

    assert entry["my_rank"] == 1
    assert entry["group_name"] == "Вторничный падел"


async def test_two_groups_come_back_as_one_list(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    """The whole point. Newest first, and the group named on each line."""
    await sign_in(client, mailer)
    me = await signed_in(session)
    first = await seed_tournament(session, rounds_to_play=7, owner=me)
    await claim_player(session, first.standings[0].player_id, me)
    second = await seed_tournament(
        session, rounds_to_play=7, owner=me, group_name="Субботний падел"
    )
    await claim_player(session, second.standings[0].player_id, me)
    await session.commit()

    body = (await client.get("/api/me/tournaments")).json()

    assert {entry["group_name"] for entry in body} == {"Вторничный падел", "Субботний падел"}
    assert [entry["id"] for entry in body] == [str(second.id), str(first.id)]


async def test_no_account_id_rides_along(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    """The list is built from account ids; none of them may reach the wire."""
    await sign_in(client, mailer)
    me = await signed_in(session)
    view = await seed_tournament(session, rounds_to_play=7, owner=me)
    await claim_player(session, view.standings[0].player_id, me)
    await session.commit()

    body = (await client.get("/api/me/tournaments")).text

    assert str(me.id) not in body
    assert "group_id" not in body
