"""What this API tells caches, which until now was the opposite of the truth.

The platform answers every function call with ``cache-control: public, max-age=0,
must-revalidate`` and no ``Vary``. Read it as a sentence and it says: any shared cache may
keep this, and nothing about who it was for. Almost every route here reads the session
cookie and answers differently because of it.

``max-age=0, must-revalidate`` is what kept that from being an incident — a conforming cache
has to come back to the origin, and with no validator to revalidate against it must fetch
afresh. But "unlikely to be served to the wrong person" is the wrong kind of guarantee for
"which account's data is this", and it depends on every intermediary being well behaved
rather than on us being clear.

These check the header on the paths that matter and, more importantly, on the kinds of
response that are easy to forget: a refusal names a group, a 401 says whether you are signed
in, and both go through a different code path from a 200.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from conftest import seed_tournament, sign_in
from padel_tour.db import PROVIDER_EMAIL
from padel_tour.services import create_group, ensure_identity

if TYPE_CHECKING:
    from httpx import AsyncClient, Response
    from sqlalchemy.ext.asyncio import AsyncSession

    from padel_tour.services.mail import InMemoryMailer


def assert_private(response: Response) -> None:
    headers = response.headers
    cache = headers.get("cache-control", "")

    assert "no-store" in cache, f"cacheable: {cache!r}"
    assert "private" in cache, f"not marked private: {cache!r}"
    assert "public" not in cache, f"offered to shared caches: {cache!r}"
    assert "Cookie" in headers.get("vary", ""), "a cache could ignore whose answer this is"


async def test_an_ordinary_read_is_private(client: AsyncClient) -> None:
    assert_private(await client.get("/api/health"))


async def test_the_most_personal_answer_of_all_is_private(
    client: AsyncClient, mailer: InMemoryMailer
) -> None:
    """``/auth/me`` is the account, by name, with every group it can open."""
    await sign_in(client, mailer)

    assert_private(await client.get("/api/auth/me"))


async def test_a_signed_out_401_is_private(client: AsyncClient) -> None:
    """Cached, this answers "not signed in" to somebody who is."""
    assert_private(await client.get("/api/auth/me"))


async def test_a_refusal_is_private(
    client: AsyncClient, session: AsyncSession, mailer: InMemoryMailer
) -> None:
    """403 goes through an exception handler rather than a route, so it is its own path."""
    other = await ensure_identity(session, PROVIDER_EMAIL, "elsewhere@example.com")
    stranger = await create_group(session, "Чужая группа", owner_account_id=other.id)
    await session.commit()
    await sign_in(client, mailer)

    response = await client.get(f"/api/groups/{stranger.id}")

    assert response.status_code == 403
    assert_private(response)


async def test_a_write_is_private(client: AsyncClient, mailer: InMemoryMailer) -> None:
    await sign_in(client, mailer)

    assert_private(await client.post("/api/groups", json={"name": "Новая"}))


@pytest.mark.parametrize("path", ["/api/groups", "/api/auth/me"])
async def test_no_answer_carries_a_stale_platform_default(
    client: AsyncClient, mailer: InMemoryMailer, path: str
) -> None:
    """The header is set, not merely absent — an unset one is where this started."""
    await sign_in(client, mailer)

    assert_private(await client.get(path))


async def test_a_tournament_open_to_the_public_is_still_private(
    client: AsyncClient, session: AsyncSession
) -> None:
    """The one route anybody with the link may read, and the tempting one to cache.

    It answers differently for the four who played court 2 than for a stranger, because the
    viewer block decides which courts offer a score box. Same URL, different body.
    """
    view = await seed_tournament(session, rounds_to_play=1)
    await session.commit()

    response = await client.get(f"/api/tournaments/{view.id}")

    assert response.status_code == 200
    assert_private(response)


async def test_the_signed_in_tests_above_were_really_signed_in(
    client: AsyncClient, mailer: InMemoryMailer
) -> None:
    """A helper that quietly did nothing would make half this file check the wrong thing."""
    await sign_in(client, mailer)

    assert (await client.get("/api/auth/me")).status_code == 200
