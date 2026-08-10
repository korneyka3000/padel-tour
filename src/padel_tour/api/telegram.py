"""Telegram webhook.

Polling cannot run on a serverless platform — there is no long-lived process to poll from.
A webhook fits exactly: it is an ordinary POST endpoint, and the handlers do not change,
because they were written against the dispatcher rather than against a transport.

The endpoint is public by necessity, so every request must carry the secret Telegram was
given when the webhook was registered.
"""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Annotated, Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import Update
from fastapi import APIRouter, Header, HTTPException, Request, status

from padel_tour.bot.config import MissingTokenError, load_config
from padel_tour.bot.handlers import router as bot_router
from padel_tour.bot.middleware import SessionMiddleware
from padel_tour.settings import settings

from .deps import session_factory
from .routes import API_PREFIX

logger = logging.getLogger(__name__)

router = APIRouter(prefix=f"{API_PREFIX}/telegram", tags=["telegram"])

#: Telegram echoes this back in a header on every webhook call.
SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"  # noqa: S105 - a header name


def webhook_secret() -> str:
    return settings().telegram_webhook_secret.strip()


@lru_cache(maxsize=1)
def _bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    """Built once per instance and reused, like the database pool."""
    config = load_config()
    bot = Bot(token=config.token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.update.middleware(SessionMiddleware(session_factory()))
    dispatcher.include_router(bot_router)
    return bot, dispatcher


@router.post("/webhook", include_in_schema=False)
async def telegram_webhook(
    request: Request,
    secret: Annotated[str | None, Header(alias=SECRET_HEADER)] = None,
) -> dict[str, bool]:
    """Hand one update to the dispatcher.

    Always answers 200 once the secret checks out. Telegram retries anything else, and a bug
    in a handler would otherwise turn into the same update arriving again and again.
    """
    expected = webhook_secret()
    if not expected:
        logger.error("TELEGRAM_WEBHOOK_SECRET is not set; refusing webhook traffic")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="webhook not configured"
        )
    if secret != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="bad secret")

    try:
        bot, dispatcher = _bot_and_dispatcher()
    except MissingTokenError:
        logger.exception("bot token missing")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="bot not configured"
        ) from None

    payload: dict[str, Any] = await request.json()
    update = Update.model_validate(payload, context={"bot": bot})

    try:
        await dispatcher.feed_update(bot, update)
    except Exception:
        logger.exception("handler failed for update %s", update.update_id)

    return {"ok": True}
