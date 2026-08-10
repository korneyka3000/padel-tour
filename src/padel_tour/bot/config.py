"""Bot configuration.

``.env`` is read by :mod:`padel_tour.settings`, which is what makes running the bot locally
a one-liner. In deployment the variables come from the environment proper and no ``.env``
exists.
"""

from __future__ import annotations

from dataclasses import dataclass

from padel_tour.settings import settings


class MissingTokenError(RuntimeError):
    """BOT_TOKEN is not set, so there is no bot to run."""


@dataclass(frozen=True, slots=True)
class BotConfig:
    token: str

    @property
    def redacted_token(self) -> str:
        """Safe to log: enough to tell two bots apart, not enough to impersonate one."""
        head, _, _ = self.token.partition(":")
        return f"{head}:…"


def load_config() -> BotConfig:
    """Read the bot's settings."""
    token = settings().bot_token.strip()
    if not token:
        raise MissingTokenError(
            "BOT_TOKEN is not set — create a bot with @BotFather and put the token in .env"
        )
    return BotConfig(token=token)
