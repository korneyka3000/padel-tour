"""How the engine is built, which only matters where it is hardest to observe.

Both settings here exist because of production, not because of a preference: one was a
silent failure in a serverless function, the other is a documented incompatibility with the
pooler that production connects through. Neither can be checked by running the suite — the
suite talks to a container, directly, in a process that never freezes — so they are asserted
rather than trusted.
"""

from __future__ import annotations

from padel_tour.db.session import POOL_RECYCLE_SECONDS, _asyncpg_options, create_engine

POOLED = "postgresql+asyncpg://u:p@ep-crimson-cell-aw66pks6-pooler.aws.neon.tech/neondb"
DIRECT = "postgresql+asyncpg://u:p@ep-crimson-cell-aw66pks6.aws.neon.tech/neondb"


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


def test_the_statement_cache_is_off_behind_a_pooler() -> None:
    """pgbouncer in transaction mode outlives no prepared statement, and a cached one
    eventually points at nothing — intermittently, under load."""
    assert _asyncpg_options(POOLED) == {"prepared_statement_cache_size": 0}


def test_a_direct_connection_keeps_its_statement_cache() -> None:
    """Every test and every local run. Prepared statements there are free performance."""
    assert _asyncpg_options(DIRECT) == {}
