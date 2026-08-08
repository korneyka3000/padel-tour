"""Bot configuration, read from the environment.

``.env`` is loaded if present, which is what makes running the bot locally a one-liner. In
deployment the variables come from the environment proper and no ``.env`` exists.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING

from dotenv import load_dotenv

if TYPE_CHECKING:
    from pathlib import Path


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


def load_config(env_file: Path | None = None) -> BotConfig:
    """Read the bot's settings, loading ``.env`` first if it is there."""
    load_dotenv(env_file, override=False)

    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        raise MissingTokenError(
            "BOT_TOKEN is not set — create a bot with @BotFather and put the token in .env"
        )
    return BotConfig(token=token)
