"""How the engine is built, which only matters where it is hardest to observe.

Both settings here exist because of production, not because of a preference: one was a
silent failure in a serverless function, the other is a documented incompatibility with the
pooler that production connects through. Neither can be exercised by the suite — it talks to
a container, directly, in a process that never freezes.

So every test here **builds an engine**. The first version of this file asserted what a
helper returned instead, which is how the pooled setting shipped as an engine keyword that
``create_async_engine`` rejects outright: the mapping was right and the thing it mapped to
did not exist. The deploy caught it; a test that constructed anything would have.
"""

from __future__ import annotations

import pytest

from padel_tour.db import MissingDatabaseError, database_url
from padel_tour.db.session import POOL_RECYCLE_SECONDS, create_engine

POOLED = "postgresql+asyncpg://u:p@ep-crimson-cell-pooler.c-12.us-east-1.aws.neon.tech/neondb"
DIRECT = "postgresql+asyncpg://u:p@ep-crimson-cell.c-12.us-east-1.aws.neon.tech/neondb"


def test_a_pooled_url_produces_a_working_engine() -> None:
    """The one the first version of this file could not have caught."""
    engine = create_engine(POOLED)

    assert engine.dialect.name == "postgresql"


def test_the_statement_cache_is_off_behind_a_pooler() -> None:
    """pgbouncer in transaction mode outlives no prepared statement, and a cached one
    eventually points at nothing — intermittently, under load."""
    engine = create_engine(POOLED)

    assert engine.url.query.get("prepared_statement_cache_size") == "0"


def test_a_direct_connection_keeps_its_statement_cache() -> None:
    """Every test and every local run. Prepared statements there are free performance."""
    engine = create_engine(DIRECT)

    assert "prepared_statement_cache_size" not in engine.url.query


def test_connections_are_checked_before_they_are_used() -> None:
    """A frozen serverless instance wakes up holding a socket the far end closed hours ago.

    Without this the next request dies on "connection is closed" — which is what happened
    to /login, and which looks to the person typing it like the bot ignoring them.
    """
    engine = create_engine(DIRECT)

    assert engine.pool._pre_ping is True


def test_connections_are_retired_before_the_far_end_drops_them() -> None:
    engine = create_engine(DIRECT)

    assert engine.pool._recycle == POOL_RECYCLE_SECONDS


def test_a_missing_database_url_says_what_to_do() -> None:
    """There used to be a fallback here, and it invented a SQLite file — a different
    database from the one the code would meet in production, which is how a migration that
    could not run locally and a suite that passed against nothing reached main (Р-034,
    Р-041). No fallback now, and the refusal carries the command that fixes it."""
    with pytest.raises(MissingDatabaseError, match="docker compose"):
        database_url()
