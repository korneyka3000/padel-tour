"""Signing in, and what being signed in changes.

Half of this is about what the endpoints refuse to say. A sign-in form that answers
differently for a known and an unknown address is a way to find out who has an account
here, and that is worth a test of its own.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from conftest import OWNER_EMAIL, seed_tournament, sign_in
from padel_tour.api.auth import link_base, secure_cookies
from padel_tour.api.deps import SESSION_COOKIE
from padel_tour.db import PROVIDER_EMAIL
from padel_tour.services import (
    account_for_identity,
    add_player,
    create_group,
    create_invite,
    ensure_identity,
)

if TYPE_CHECKING:
    import pytest
    from httpx import AsyncClient
    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.db import Account
    from padel_tour.services.mail import InMemoryMailer


async def signed_in_account(session: AsyncSession, address: str = OWNER_EMAIL) -> Account:
    account = await account_for_identity(session, PROVIDER_EMAIL, address)
    assert account is not None
    return account


async def somebody_else(session: AsyncSession) -> Account:
    """A real account that is not the one signing in. A group needs an owner that exists."""
    return await ensure_identity(session, PROVIDER_EMAIL, "elsewhere@example.com")


# -------------------------------------------------------------------------------- asking


async def test_a_link_is_sent(client: AsyncClient, mailer: InMemoryMailer) -> None:
    response = await client.post("/api/auth/magic-link", json={"email": OWNER_EMAIL})

    assert response.status_code == 202
    assert mailer.last_to(OWNER_EMAIL) is not None


async def test_an_unknown_address_gets_the_same_answer(client: AsyncClient) -> None:
    """Otherwise the form tells anyone who asks who has an account here."""
    known = await client.post("/api/auth/magic-link", json={"email": OWNER_EMAIL})
    unknown = await client.post("/api/auth/magic-link", json={"email": "nobody@example.com"})

    assert known.status_code == unknown.status_code == 202
    assert known.json() == unknown.json()


async def test_a_second_request_within_the_minute_is_429(client: AsyncClient) -> None:
    await client.post("/api/auth/magic-link", json={"email": OWNER_EMAIL})
    again = await client.post("/api/auth/magic-link", json={"email": OWNER_EMAIL})

    assert again.status_code == 429


async def test_a_malformed_address_is_refused_before_anything_is_sent(
    client: AsyncClient, mailer: InMemoryMailer
) -> None:
    response = await client.post("/api/auth/magic-link", json={"email": "не почта"})

    assert response.status_code == 422
    assert mailer.sent == []


# ------------------------------------------------------------------------------ entering


async def test_following_the_link_sets_a_cookie(
    client: AsyncClient, mailer: InMemoryMailer
) -> None:
    await sign_in(client, mailer)
    assert client.cookies.get(SESSION_COOKIE)


async def test_the_cookie_cannot_be_read_by_script(
    client: AsyncClient, mailer: InMemoryMailer
) -> None:
    """A session token in reach of injected script is a session token that leaves."""
    await client.post("/api/auth/magic-link", json={"email": OWNER_EMAIL})
    message = mailer.last_to(OWNER_EMAIL)
    assert message is not None
    token = message.body.partition("?token=")[2].split()[0]

    response = await client.post("/api/auth/enter", json={"token": token})
    header = response.headers["set-cookie"].lower()
    assert "httponly" in header
    assert "samesite=lax" in header


async def test_a_made_up_token_is_refused(client: AsyncClient) -> None:
    response = await client.post("/api/auth/enter", json={"token": "not-a-real-token"})
    assert response.status_code == 400


# ------------------------------------------------------------------------------------ me


async def test_me_without_a_cookie_is_401(client: AsyncClient) -> None:
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_me_names_the_groups_you_are_in(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    await sign_in(client, mailer)
    await seed_tournament(session, owner=await signed_in_account(session))
    await session.commit()

    body = (await client.get("/api/auth/me")).json()
    assert [group["name"] for group in body["groups"]] == ["Вторничный падел"]


async def test_signing_out_ends_the_session(client: AsyncClient, mailer: InMemoryMailer) -> None:
    await sign_in(client, mailer)

    assert (await client.post("/api/auth/sign-out")).status_code == 204
    assert (await client.get("/api/auth/me")).status_code == 401


async def test_signing_out_twice_is_not_an_error(client: AsyncClient) -> None:
    """The caller asked to be signed out, and they are."""
    assert (await client.post("/api/auth/sign-out")).status_code == 204


# ------------------------------------------------------------------------------ visibility


async def test_groups_are_empty_when_signed_out(client: AsyncClient, session: AsyncSession) -> None:
    await seed_tournament(session)
    await session.commit()

    assert (await client.get("/api/groups")).json() == []


async def test_a_signed_out_request_is_not_the_system(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The regression this whole distinction exists for.

    To the service layer ``None`` means *system* — the CLI, a migration — and is trusted
    with everything. If a request with no cookie arrived as ``None``, every private group in
    the database would be readable by anyone who asked, and quietly.
    """
    view = await seed_tournament(session, owner=await somebody_else(session))
    await session.commit()

    assert (await client.get(f"/api/groups/{view.group_id}")).status_code == 401
    assert (await client.get(f"/api/groups/{view.group_id}/tournaments")).status_code == 401
    assert (await client.get(f"/api/groups/{view.group_id}/active")).status_code == 401


async def test_somebody_elses_group_is_403(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    """403 rather than 404: "ask for an invitation" is actionable, "broken link" is a lie."""
    other = await somebody_else(session)
    stranger = await create_group(session, "Чужая группа", owner_account_id=other.id)
    await session.commit()
    await sign_in(client, mailer)

    response = await client.get(f"/api/groups/{stranger.id}")
    assert response.status_code == 403
    assert response.json()["detail"]


async def test_a_tournament_is_open_to_anyone_with_the_link(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The point of a link is to show somebody the table.

    The group around it is closed and the caller is signed out — the tournament still opens.
    """
    view = await seed_tournament(session, rounds_to_play=1, owner=await somebody_else(session))
    await session.commit()

    assert (await client.get(f"/api/groups/{view.group_id}")).status_code == 401
    assert (await client.get(f"/api/tournaments/{view.id}")).status_code == 200


# ----------------------------------------------------------------------------- invitations


async def test_the_owner_issues_an_invitation(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    await sign_in(client, mailer)
    owner = await signed_in_account(session)
    group = await create_group(session, "Вторничный падел", owner_account_id=owner.id)
    anya = await add_player(session, group.id, "Аня", actor=owner)
    await session.commit()

    response = await client.post(f"/api/players/{anya.id}/invite")
    assert response.status_code == 200
    assert response.json()["player"]["name"] == "Аня"
    assert response.json()["token"]


async def test_a_stranger_cannot_issue_an_invitation(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    other = await somebody_else(session)
    group = await create_group(session, "Чужая", owner_account_id=other.id)
    anya = await add_player(session, group.id, "Аня", actor=other)
    await session.commit()
    await sign_in(client, mailer)

    assert (await client.post(f"/api/players/{anya.id}/invite")).status_code == 403


async def test_an_invitation_says_who_it_is_for_without_signing_in(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The page has to say "join as Аня" before it asks anyone for an address."""
    group = await create_group(session, "Вторничный падел")
    anya = await add_player(session, group.id, "Аня")
    token = await create_invite(session, None, anya.id)
    await session.commit()

    response = await client.get(f"/api/invites/{token}")
    assert response.status_code == 200
    assert response.json()["name"] == "Аня"


async def test_redeeming_binds_the_account_to_that_player(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    group = await create_group(session, "Вторничный падел")
    anya = await add_player(session, group.id, "Аня")
    token = await create_invite(session, None, anya.id)
    await session.commit()
    await sign_in(client, mailer, "anya@example.com")

    response = await client.post("/api/invites/redeem", json={"token": token})
    assert response.status_code == 200
    assert response.json()["id"] == str(anya.id)

    body = (await client.get("/api/auth/me")).json()
    assert [group["name"] for group in body["groups"]] == ["Вторничный падел"]


async def test_redeeming_needs_an_account(client: AsyncClient, session: AsyncSession) -> None:
    group = await create_group(session, "Вторничный падел")
    anya = await add_player(session, group.id, "Аня")
    token = await create_invite(session, None, anya.id)
    await session.commit()

    assert (await client.post("/api/invites/redeem", json={"token": token})).status_code == 401


# --------------------------------------------------------------------------------- roster


async def test_a_signed_in_person_can_start_a_group(
    client: AsyncClient, mailer: InMemoryMailer
) -> None:
    """Without this, signing in leads to an empty page and no way off it."""
    await sign_in(client, mailer)

    created = await client.post("/api/groups", json={"name": "Вторничный падел"})
    assert created.status_code == 201

    added = await client.post(f"/api/groups/{created.json()['id']}/players", json={"name": "Аня"})
    assert added.status_code == 201
    assert [player["name"] for player in added.json()["players"]] == ["Аня"]

    assert [group["name"] for group in (await client.get("/api/groups")).json()] == [
        "Вторничный падел"
    ]


async def test_starting_a_group_needs_an_account(client: AsyncClient) -> None:
    assert (await client.post("/api/groups", json={"name": "Ничья"})).status_code == 401


# ------------------------------------------------------------------------------ addresses


def test_the_link_falls_back_to_the_platform_domain(monkeypatch: pytest.MonkeyPatch) -> None:
    """A fresh deployment must send working links before anyone configures anything."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "yo-padel-tour.vercel.app")

    assert link_base() == "https://yo-padel-tour.vercel.app/auth/enter"
    assert secure_cookies()


def test_a_configured_address_wins(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://padel.example.com/")
    monkeypatch.setenv("VERCEL_PROJECT_PRODUCTION_URL", "yo-padel-tour.vercel.app")

    assert link_base() == "https://padel.example.com/auth/enter"


def test_a_developer_machine_does_not_demand_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    """A Secure cookie over plain http is never stored, and the session silently vanishes."""
    monkeypatch.delenv("PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("VERCEL_PROJECT_PRODUCTION_URL", raising=False)

    assert link_base() == "http://localhost:5173/auth/enter"
    assert not secure_cookies()
