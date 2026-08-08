"""Telegram bot.

The interface people actually use, standing on a court. Its defining constraint is that it
owns **one message per tournament** and rewrites it rather than posting a running
commentary — see :mod:`padel_tour.bot.screen_store`.

Screens are pure functions of state (:mod:`padel_tour.bot.screens`), so the whole interface
can be tested without Telegram.

Only configuration is re-exported here. The command line lives in :mod:`padel_tour.bot.app`
and is imported on demand: pulling it in from this file would mean anything touching the bot
— including the webhook running in a serverless function — dragging a CLI framework along
with it.

Requires the ``bot`` and ``db`` extras.
"""

from .config import BotConfig, MissingTokenError, load_config

__all__ = ["BotConfig", "MissingTokenError", "load_config"]
