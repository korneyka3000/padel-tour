"""Everything this process reads from its environment, in one typed object.

Before this there were ten ``os.environ.get`` calls in six modules. Nothing declared what
the application actually needs, nothing validated it, and a typo in a variable name fell
silently through to a default — which for ``SMTP_HOST`` means "development", so a
misspelled production setting looks exactly like no setting at all.

**Read at call time, not at import, and not cached.** An object built during import would
freeze whatever the shell happened to hold, and a cached one goes stale the moment a test
moves a variable underneath it. Building one costs about 110 microseconds — measured, not
assumed — against one to three calls per request, so caching would buy half a millisecond
and cost a whole class of bug where the environment says one thing and the process believes
another.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Local database file used when ``DATABASE_URL`` is unset. A fresh checkout runs with no
#: setup at all, which is the point.
DEFAULT_SQLITE_PATH = "padel.db"

#: Where the Vite dev server lives. The default for a checkout nobody has deployed.
DEFAULT_BASE_URL = "http://localhost:5173"

DEFAULT_SMTP_PORT = 587

#: Which dotenv file to read, or ``None`` for none at all.
#:
#: A module-level knob rather than a constructor argument because the tests have to turn it
#: off, and they must. A developer's ``.env`` holds a real bot token and a real database
#: URL; a suite that reads it is a suite that can reach production by accident. The bot was
#: the only thing loading ``.env`` before this module existed, so nothing else regresses by
#: making the file explicit here.
ENV_FILE: str | None = ".env"


class Settings(BaseSettings):
    """The environment, declared.

    Defaults describe a fresh checkout: SQLite in a file, mail to the log, no bot. Anything
    that must be set to run in production is checked where it is used, with a message
    naming the variable — a validation error at import would take the whole app down for a
    missing bot token that only the bot needs.
    """

    model_config = SettingsConfigDict(
        env_file_encoding="utf-8",
        extra="ignore",
        # Vercel and Docker hand us plenty of variables that are not ours.
        case_sensitive=False,
    )

    database_url: str = ""
    #: Only tests set this. Unset means the suite runs on in-memory SQLite.
    test_database_url: str = ""

    bot_token: str = ""
    telegram_webhook_secret: str = ""

    smtp_host: str = ""
    smtp_port: int = DEFAULT_SMTP_PORT
    smtp_user: str = ""
    smtp_password: str = ""
    mail_from: str = ""

    public_base_url: str = ""
    #: The bot's @username. With a Main Mini App enabled — @BotFather, /mybots, Bot
    #: Settings, Configure Mini App — this is all a ``t.me`` launch link needs; there is no
    #: app short name any more. Unset, buttons fall back to an ordinary link and Telegram's
    #: in-app browser.
    bot_username: str = ""

    #: Telegram user ids that may see and run everything, comma separated.
    #:
    #: A capability, not a separate surface. An admin uses the same screens as everyone
    #: else and simply is not stopped by membership — which is what somebody fixing a
    #: group's tournament at eleven at night actually needs. A second interface would be a
    #: second thing to keep working, and would still be missing whatever went wrong.
    #:
    #: Nothing stops an admin from also being an ordinary player: the identity is the same,
    #: and being listed here adds permission rather than replacing anything.
    admin_telegram_ids: str = ""

    @property
    def admins(self) -> frozenset[str]:
        return frozenset(
            part.strip() for part in self.admin_telegram_ids.split(",") if part.strip()
        )

    #: Set by the platform, not by us. The fallback that makes a first deploy work before
    #: anybody has thought about ``PUBLIC_BASE_URL``.
    vercel_project_production_url: str = Field(default="")

    @property
    def sender(self) -> str:
        """Who mail comes from. Gmail rewrites a From that is not the account, so default
        to the account rather than to something that would be silently replaced."""
        return self.mail_from or self.smtp_user


def settings() -> Settings:
    """The environment as it stands right now."""
    return Settings(_env_file=ENV_FILE)


def base_url() -> str:
    """Where this deployment lives.

    Falls back to the domain the platform already knows about, so a fresh deployment sends
    working sign-in links before anyone has configured anything. Set ``PUBLIC_BASE_URL``
    once there is a real domain — the platform's variable follows the project, not the
    address people actually type.

    Lives here rather than in the API because the bot needs it too, for the link that takes
    a chat to the full chart, and the bot has no business importing an HTTP router.
    """
    current = settings()
    configured = current.public_base_url.strip().rstrip("/")
    if configured:
        return configured

    platform = current.vercel_project_production_url.strip().rstrip("/")
    if platform:
        return platform if "://" in platform else f"https://{platform}"

    return DEFAULT_BASE_URL


def mini_app_url(start_param: str = "") -> str:
    """A link that opens the Mini App inside Telegram, or an ordinary web link.

    In a group chat a ``web_app`` button is not available — Telegram allows those only in
    private chats — but a **direct link** does work there, which is what this builds. The
    app opens full-screen inside the client, already signed in, because Telegram hands the
    page a signed statement of who pressed the button.

    ``t.me/<bot>?startapp=<param>``, with no app short name in it: that was the older
    ``/newapp`` shape, and a Main Mini App — Bot Settings, Configure Mini App — launches
    from the bot's username alone.

    Falls back to the plain site when no username is configured. That still works; it just
    opens in the in-app browser as a stranger, and this is the difference between a chart
    the group can poke at and one it can only look at.
    """
    bot = settings().bot_username.strip().lstrip("@")
    if not bot:
        return f"{base_url()}/{start_param.replace('_', '/', 1)}" if start_param else base_url()

    suffix = f"?startapp={start_param}" if start_param else "?startapp"
    return f"https://t.me/{bot}{suffix}"


__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_SMTP_PORT",
    "DEFAULT_SQLITE_PATH",
    "ENV_FILE",
    "Settings",
    "base_url",
    "mini_app_url",
    "settings",
]
