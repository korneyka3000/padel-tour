"""The accounts migration moves data, not just columns.

A migration that creates the new shape but drops what was in the old one is worse than no
migration: it loses the binding between a chat and its group, and between a tournament and
whoever runs it. These tests write the old shape, migrate, and check the data arrived.

They run Alembic against a real database rather than calling the revision's functions, so
what is tested is what will actually run.
"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import text

from padel_tour.db import PROVIDER_TELEGRAM, create_engine
from padel_tour.db.config import normalise_url

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from sqlalchemy.ext.asyncio import AsyncEngine

ROOT = Path(__file__).resolve().parents[2]

CHAT_ID = -100500
ORGANISER_TG = 4242

#: Pinned so the test keeps meaning what it says once later revisions arrive.
ACCOUNTS_REVISION = "accounts"
BEFORE_ACCOUNTS = "d79a4a4829cb"


def alembic_config() -> Config:
    config = Config(str(ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(ROOT / "migrations"))
    return config


async def migrate_to(revision: str) -> None:
    """Run Alembic from a worker thread.

    `migrations/env.py` calls `asyncio.run()`, which refuses to start inside a loop that is
    already running — and these tests are async. A fresh thread has no loop of its own.
    """
    await asyncio.to_thread(command.upgrade, alembic_config(), revision)


async def rollback_to(revision: str) -> None:
    await asyncio.to_thread(command.downgrade, alembic_config(), revision)


@pytest.fixture
async def migrated_engine(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[AsyncEngine]:
    """A database at the revision just before accounts, seeded with the old shape.

    No longer skipped when nobody set an environment variable. These are the tests that
    catch a migration which cannot execute, and they used to be exactly the ones a person
    running the suite locally never saw.
    """
    url = database_url
    monkeypatch.setenv("DATABASE_URL", url)

    await rollback_to("base")
    await migrate_to(BEFORE_ACCOUNTS)

    engine = create_engine(normalise_url(url))
    try:
        yield engine
    finally:
        await engine.dispose()
        await rollback_to("base")


async def seed_old_shape(engine: AsyncEngine) -> tuple[str, str]:
    """A group bound to a chat, and a tournament run from Telegram."""
    async with engine.begin() as connection:
        group_id = (
            await connection.execute(
                text("""
                INSERT INTO groups (id, name, telegram_chat_id)
                VALUES (gen_random_uuid(), 'Вторник', :chat)
                RETURNING id
                """),
                {"chat": CHAT_ID},
            )
        ).scalar_one()

        tournament_id = (
            await connection.execute(
                text("""
                INSERT INTO tournaments (
                    id, group_id, format, points_per_match, pairing_pattern,
                    total_rounds, seed, status, organiser_telegram_id
                )
                VALUES (
                    gen_random_uuid(), :group, 'americano', 24, 'crossover',
                    7, 1, 'active', :organiser
                )
                RETURNING id
                """),
                {"group": group_id, "organiser": ORGANISER_TG},
            )
        ).scalar_one()

    return str(group_id), str(tournament_id)


async def test_the_chat_binding_survives(
    migrated_engine: AsyncEngine,
) -> None:
    group_id, _ = await seed_old_shape(migrated_engine)
    await migrate_to(ACCOUNTS_REVISION)

    async with migrated_engine.connect() as connection:
        row = (
            await connection.execute(
                text("SELECT group_id, provider, external_id FROM group_links")
            )
        ).one()
    assert str(row.group_id) == group_id
    assert row.provider == PROVIDER_TELEGRAM
    assert row.external_id == str(CHAT_ID)


async def test_the_organiser_becomes_an_account(
    migrated_engine: AsyncEngine,
) -> None:
    _, tournament_id = await seed_old_shape(migrated_engine)
    await migrate_to(ACCOUNTS_REVISION)

    async with migrated_engine.connect() as connection:
        organiser = (
            await connection.execute(
                text("SELECT organiser_account_id FROM tournaments WHERE id = :id"),
                {"id": tournament_id},
            )
        ).scalar_one()
        identity = (
            await connection.execute(
                text("""
                SELECT account_id, external_id FROM identities
                WHERE provider = :provider
                """),
                {"provider": PROVIDER_TELEGRAM},
            )
        ).one()

    assert organiser is not None
    assert str(identity.account_id) == str(organiser)
    assert identity.external_id == str(ORGANISER_TG)


async def test_the_old_columns_are_gone(
    migrated_engine: AsyncEngine,
) -> None:
    await seed_old_shape(migrated_engine)
    await migrate_to(ACCOUNTS_REVISION)

    async with migrated_engine.connect() as connection:
        columns = set(
            (
                await connection.execute(
                    text("""
                    SELECT column_name FROM information_schema.columns
                    WHERE table_name IN ('groups', 'tournaments')
                    """)
                )
            )
            .scalars()
            .all()
        )
    assert "telegram_chat_id" not in columns
    assert "organiser_telegram_id" not in columns
    assert "organiser_account_id" in columns


async def test_downgrade_puts_the_data_back(
    migrated_engine: AsyncEngine,
) -> None:
    """A migration you cannot reverse is a migration you cannot deploy with confidence."""
    group_id, tournament_id = await seed_old_shape(migrated_engine)
    await migrate_to(ACCOUNTS_REVISION)
    await rollback_to(BEFORE_ACCOUNTS)

    async with migrated_engine.connect() as connection:
        chat = (
            await connection.execute(
                text("SELECT telegram_chat_id FROM groups WHERE id = :id"),
                {"id": group_id},
            )
        ).scalar_one()
        organiser = (
            await connection.execute(
                text("SELECT organiser_telegram_id FROM tournaments WHERE id = :id"),
                {"id": tournament_id},
            )
        ).scalar_one()

    assert chat == CHAT_ID
    assert organiser == ORGANISER_TG


@pytest.mark.usefixtures("migrated_engine")
async def test_running_a_migration_does_not_silence_the_application() -> None:
    """Alembic configures logging, and its default takes the application's loggers with it.

    ``fileConfig`` disables every logger that already exists unless told otherwise, and by
    the time ``migrations/env.py`` runs it, importing the models has created all of ours.
    The damage outlives the migration: in a test run it swallows later assertions about log
    output, and in a process that migrates before serving it would swallow the warning that
    says a sign-in link went to the log instead of an inbox.
    """
    logger = logging.getLogger("padel_tour.services.mail")
    assert not logger.disabled

    await migrate_to(ACCOUNTS_REVISION)

    assert not logger.disabled


async def test_every_migration_applies_and_reverses(
    database_url: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The whole chain, both ways, including whichever revision was added this week.

    Used to be a CI step, which meant it ran after the code was pushed rather than before.
    It also only ever covered ``head`` as of the last time somebody looked at the workflow;
    here it follows the chain wherever it goes.
    """
    monkeypatch.setenv("DATABASE_URL", database_url)
    await rollback_to("base")

    await migrate_to("head")
    await rollback_to("base")
