"""Telegram bot.

The interface people actually use, standing on a court. Its defining constraint is that it
owns **one message per tournament** and rewrites it rather than posting a running
commentary — see :mod:`padel_tour.bot.screen_store`.

Screens are pure functions of state (:mod:`padel_tour.bot.screens`), so the whole interface
can be tested without Telegram.

Requires the ``bot`` and ``db`` extras.
"""

from .app import cli, main
from .config import BotConfig, MissingTokenError, load_config

__all__ = ["BotConfig", "MissingTokenError", "cli", "load_config", "main"]
