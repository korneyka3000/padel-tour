"""Running the bot.

    uv run padel-tour-bot poll                     # local development
    uv run padel-tour-bot set-webhook https://…    # point Telegram at a deployment
    uv run padel-tour-bot webhook-info

Polling and webhooks are two transports over the same dispatcher; the handlers know about
neither. In production the bot is served by the API's webhook endpoint, because a serverless
platform has no long-lived process to poll from. Polling stays for local work — running a
tunnel to check one button is not worth it.
"""

from __future__ import annotations

import asyncio
import logging
import secrets
from typing import Annotated

import typer
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from padel_tour.db import (
    create_all,
    create_engine,
    create_session_factory,
    database_url,
    is_sqlite,
)

from .config import MissingTokenError, load_config
from .handlers import router
from .middleware import SessionMiddleware

logger = logging.getLogger(__name__)

cli = typer.Typer(
    name="padel-tour-bot",
    help="Run or configure the padel Telegram bot.",
    no_args_is_help=True,
    add_completion=False,
)

#: What Telegram offers when somebody types a slash.
#:
#: Only a menu — an unlisted command still reaches its handler — but a command nobody can
#: discover is a command nobody uses, and /login was exactly that.
COMMANDS = [
    BotCommand(command="start", description="Начать и показать текущий экран"),
    BotCommand(command="add", description="Добавить игроков: /add Аня, Боря"),
    BotCommand(command="rename", description="Переименовать: /rename Аня = Анна"),
    BotCommand(command="tournament", description="Показать экран турнира заново"),
    BotCommand(command="login", description="Ссылка для входа на сайт (в личке)"),
]

#: Length of a generated webhook secret, in bytes before hex encoding.
SECRET_BYTES = 32


def make_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


async def _open_database() -> object:
    url = database_url()
    engine = create_engine(url)
    if is_sqlite(url):
        # The local SQLite file is the development database; anything else has had
        # migrations run against it.
        await create_all(engine)
    return engine


async def _poll() -> None:
    config = load_config()
    engine = await _open_database()

    bot = make_bot(config.token)
    dispatcher = Dispatcher()
    dispatcher.update.middleware(SessionMiddleware(create_session_factory(engine)))  # ty: ignore[invalid-argument-type]
    dispatcher.include_router(router)

    try:
        me = await bot.get_me()
        logger.info("polling as @%s (%s)", me.username, config.redacted_token)
        await bot.set_my_commands(COMMANDS)
        # Anything queued while the bot was down is stale by the time it comes back: the
        # screen those buttons belonged to has moved on.
        await bot.delete_webhook(drop_pending_updates=True)
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()
        await engine.dispose()  # ty: ignore[unresolved-attribute]


@cli.command()
def poll() -> None:
    """Run the bot locally by polling Telegram."""
    _configure_logging()
    try:
        asyncio.run(_poll())
    except MissingTokenError as exc:
        logger.error("%s", exc)  # noqa: TRY400 - a config mistake, not a crash to trace
        raise typer.Exit(1) from None
    except KeyboardInterrupt:
        logger.info("stopped")


@cli.command(name="set-webhook")
def set_webhook(
    base_url: Annotated[str, typer.Argument(help="Public base URL, e.g. https://x.vercel.app")],
    secret: Annotated[
        str | None,
        typer.Option(help="Shared secret. Generated if omitted — copy it into the deployment."),
    ] = None,
) -> None:
    """Point Telegram at a deployment's webhook endpoint."""
    _configure_logging()
    token_secret = secret or secrets.token_hex(SECRET_BYTES)
    url = f"{base_url.rstrip('/')}/api/telegram/webhook"

    async def run() -> None:
        config = load_config()
        bot = make_bot(config.token)
        try:
            await bot.set_my_commands(COMMANDS)
            await bot.set_webhook(
                url=url,
                secret_token=token_secret,
                drop_pending_updates=True,
            )
        finally:
            await bot.session.close()

    try:
        asyncio.run(run())
    except MissingTokenError as exc:
        logger.error("%s", exc)  # noqa: TRY400
        raise typer.Exit(1) from None

    typer.echo(f"Webhook set to {url}")
    if secret is None:
        typer.echo("\nAdd this to the deployment's environment, then redeploy:")
        typer.echo(f"  TELEGRAM_WEBHOOK_SECRET={token_secret}")


@cli.command(name="webhook-info")
def webhook_info() -> None:
    """Show what Telegram currently thinks the webhook is."""
    _configure_logging()

    async def run() -> None:
        config = load_config()
        bot = make_bot(config.token)
        try:
            info = await bot.get_webhook_info()
            typer.echo(f"url: {info.url or '(none — polling)'}")
            typer.echo(f"pending updates: {info.pending_update_count}")
            if info.last_error_message:
                typer.echo(f"last error: {info.last_error_message}")
        finally:
            await bot.session.close()

    try:
        asyncio.run(run())
    except MissingTokenError as exc:
        logger.error("%s", exc)  # noqa: TRY400
        raise typer.Exit(1) from None


@cli.command(name="drop-webhook")
def drop_webhook() -> None:
    """Go back to polling by removing the webhook."""
    _configure_logging()

    async def run() -> None:
        config = load_config()
        bot = make_bot(config.token)
        try:
            await bot.delete_webhook(drop_pending_updates=True)
        finally:
            await bot.session.close()

    try:
        asyncio.run(run())
    except MissingTokenError as exc:
        logger.error("%s", exc)  # noqa: TRY400
        raise typer.Exit(1) from None
    typer.echo("Webhook removed; polling will work again.")


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-5s %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
