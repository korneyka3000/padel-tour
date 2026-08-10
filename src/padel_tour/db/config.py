"""Where the database lives.

One knob: ``DATABASE_URL``. Unset means a local SQLite file, which is what makes
``padel-tour play`` work on a fresh checkout with no setup at all.
"""

from __future__ import annotations

from pathlib import Path

from padel_tour.settings import DEFAULT_SQLITE_PATH as _DEFAULT_SQLITE_NAME
from padel_tour.settings import settings

#: Local database file used when ``DATABASE_URL`` is unset.
DEFAULT_SQLITE_PATH = Path(_DEFAULT_SQLITE_NAME)

_ASYNC_DRIVERS = {
    "postgresql": "postgresql+asyncpg",
    "postgres": "postgresql+asyncpg",
    "sqlite": "sqlite+aiosqlite",
}

#: Query parameters libpq understands but asyncpg does not. Neon hands out connection
#: strings carrying these; passing them straight to asyncpg is a TypeError at connect time.
_LIBPQ_ONLY_PARAMS = ("sslmode", "channel_binding")


def normalise_url(url: str) -> str:
    """Turn any Postgres or SQLite URL into one SQLAlchemy's async engine accepts.

    Adds the async driver if the scheme has none, and drops libpq-only query parameters so
    a connection string copied straight out of the Neon console just works.
    """
    scheme, separator, rest = url.partition("://")
    if not separator:
        return url

    base, _, query = rest.partition("?")
    if query:
        kept = [
            part for part in query.split("&") if part and not part.startswith(_LIBPQ_ONLY_PARAMS)
        ]
        rest = f"{base}?{'&'.join(kept)}" if kept else base

    return f"{_ASYNC_DRIVERS.get(scheme, scheme)}://{rest}"


def database_url() -> str:
    """The async database URL for this process."""
    configured = settings().database_url.strip()
    if configured:
        return normalise_url(configured)
    return f"sqlite+aiosqlite:///{DEFAULT_SQLITE_PATH}"


def is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")
