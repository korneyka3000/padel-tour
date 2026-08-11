"""Alembic environment.

The URL always comes from :func:`padel_tour.db.database_url`, never from ``alembic.ini`` —
one place decides which database we are talking to, and it is the same one the application
uses.
"""

from __future__ import annotations

import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy.engine import Connection

from padel_tour.db import Base, create_engine, database_url

config = context.config

if config.config_file_name is not None:
    # ``disable_existing_loggers`` defaults to True, and Alembic's own template leaves it
    # there. It means every logger created before this line goes silent — which is every
    # ``padel_tour.*`` logger, because importing the models above is what created them.
    # In a test run that swallows later assertions about log output; running migrations
    # in-process it would swallow the application's own warnings, including the one saying
    # a sign-in link went to the log instead of an inbox.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _configure(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )


def run_migrations_offline() -> None:
    """Emit SQL to stdout without connecting."""
    context.configure(
        url=database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    _configure(connection)
    with context.begin_transaction():
        context.run_migrations()


async def run_migrations_online() -> None:
    """Connect and run migrations against the live database."""
    engine = create_engine(database_url())
    async with engine.connect() as connection:
        await connection.run_sync(_run)
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(run_migrations_online())
