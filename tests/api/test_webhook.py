"""The webhook endpoint.

It is publicly reachable by necessity, so the secret is the only thing standing between
Telegram's updates and anyone else's.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from padel_tour.api import telegram
from padel_tour.bot.config import MissingTokenError

if TYPE_CHECKING:
    from httpx import AsyncClient

SECRET = "s3cret-token"  # noqa: S105 - a fixture, not a credential
HEADER = telegram.SECRET_HEADER

UPDATE = {
    "update_id": 1,
    "message": {
        "message_id": 10,
        "date": 1_700_000_000,
        "chat": {"id": -100500, "type": "group", "title": "Вторничный падел"},
        "from": {"id": 42, "is_bot": False, "first_name": "Аня"},
        "text": "/start",
    },
}


@pytest.fixture(autouse=True)
def _reset_bot_cache() -> None:
    """The bot is built once per process; tests must not inherit each other's."""
    telegram._bot_and_dispatcher.cache_clear()


async def test_without_a_configured_secret_the_endpoint_refuses_traffic(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Better to answer 503 than to accept updates from anyone at all."""
    monkeypatch.delenv("TELEGRAM_WEBHOOK_SECRET", raising=False)
    response = await client.post("/api/telegram/webhook", json=UPDATE)
    assert response.status_code == 503


async def test_a_wrong_secret_is_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    response = await client.post("/api/telegram/webhook", json=UPDATE, headers={HEADER: "wrong"})
    assert response.status_code == 401


async def test_a_missing_secret_header_is_rejected(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    assert (await client.post("/api/telegram/webhook", json=UPDATE)).status_code == 401


async def test_without_a_bot_token_the_endpoint_says_so(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    monkeypatch.setenv("BOT_TOKEN", "")
    # load_config falls back to .env, which a developer machine may have.
    monkeypatch.setattr(telegram, "load_config", _raise_missing_token)

    response = await client.post("/api/telegram/webhook", json=UPDATE, headers={HEADER: SECRET})
    assert response.status_code == 503


def _raise_missing_token() -> None:
    raise MissingTokenError("BOT_TOKEN is not set")


async def test_a_valid_update_reaches_the_dispatcher(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)
    seen = []

    class FakeDispatcher:
        async def feed_update(self, _bot: object, update: object) -> None:
            seen.append(update)

    monkeypatch.setattr(telegram, "_bot_and_dispatcher", lambda: (object(), FakeDispatcher()))

    response = await client.post("/api/telegram/webhook", json=UPDATE, headers={HEADER: SECRET})
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert len(seen) == 1
    assert seen[0].update_id == 1


async def test_a_failing_handler_still_answers_200(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Telegram retries anything else, so a bug would arrive again and again."""
    monkeypatch.setenv("TELEGRAM_WEBHOOK_SECRET", SECRET)

    class ExplodingDispatcher:
        async def feed_update(self, _bot: object, _update: object) -> None:
            raise RuntimeError("handler blew up")

    monkeypatch.setattr(telegram, "_bot_and_dispatcher", lambda: (object(), ExplodingDispatcher()))

    response = await client.post("/api/telegram/webhook", json=UPDATE, headers={HEADER: SECRET})
    assert response.status_code == 200
