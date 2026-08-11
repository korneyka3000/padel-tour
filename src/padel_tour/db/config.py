"""Where the database lives.

One knob and one dialect: ``DATABASE_URL``, pointing at Postgres.

SQLite used to be the default for a fresh checkout, and it cost more than it saved. Two
dialects meant migrations that could not run locally, constraints SQLite ignored, and a
suite that passed against a database nobody deployed — see Р-034 and Р-041. ``docker
compose up`` is the replacement, and it is one command.
"""

from __future__ import annotations

from padel_tour.settings import settings


class MissingDatabaseError(RuntimeError):
    """Nothing said which database to use, and there is nothing sensible to guess."""


#: Local database file used when ``DATABASE_URL`` is unset.
_ASYNC_DRIVERS = {
    "postgresql": "postgresql+asyncpg",
    "postgres": "postgresql+asyncpg",
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
    """The async database URL for this process.

    Required. There is no fallback to invent one, because every fallback we had invented a
    *different* database from the one the code would meet in production.
    """
    configured = settings().database_url.strip()
    if not configured:
        raise MissingDatabaseError(
            "DATABASE_URL is not set. Start one with `docker compose up -d` and point at it: "
            "postgresql://padel:padel@localhost:55432/padel"
        )
    return normalise_url(configured)
