"""Wiring and entry point.

    uv run padel-tour-bot

Polling, not webhooks: no public address and no certificate to arrange, which is plenty for
a group chat. Moving to webhooks later is one setting, not a rewrite.
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from padel_tour.db import create_all, create_engine, create_session_factory, database_url, is_sqlite

from .config import MissingTokenError, load_config
from .handlers import router
from .middleware import SessionMiddleware

logger = logging.getLogger(__name__)

COMMANDS = [
    BotCommand(command="start", description="Начать и показать текущий экран"),
    BotCommand(command="add", description="Добавить игроков: /add Аня, Боря"),
    BotCommand(command="tournament", description="Показать экран турнира заново"),
]


async def run() -> None:
    """Start the bot and poll until interrupted."""
    config = load_config()

    url = database_url()
    engine = create_engine(url)
    if is_sqlite(url):
        # The local SQLite file is the development database; anything else has had
        # migrations run against it.
        await create_all(engine)

    bot = Bot(
        token=config.token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dispatcher = Dispatcher()
    dispatcher.update.middleware(SessionMiddleware(create_session_factory(engine)))
    dispatcher.include_router(router)

    try:
        me = await bot.get_me()
        logger.info("starting @%s (%s)", me.username, config.redacted_token)
        await bot.set_my_commands(COMMANDS)
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()


def main() -> int:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    try:
        asyncio.run(run())
    except MissingTokenError as exc:
        logger.error("%s", exc)  # noqa: TRY400 - a config mistake, not a crash to trace
        return 1
    except KeyboardInterrupt:
        logger.info("stopped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
