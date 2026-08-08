"""Accounts and identities

Our Account becomes the identity; Telegram becomes one way of arriving at it. That means
moving two Telegram-shaped columns out of the domain and into link tables — and moving the
data with them, which autogenerate cannot do.

Constraints are named explicitly. Autogenerate emits `op.drop_constraint(None, ...)`, which
fails on Postgres because there is nothing to drop by that name.

Revision ID: accounts
Revises: d79a4a4829cb
Create Date: 2026-08-09
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# Custom column types are rendered fully qualified by autogenerate, so the module has to be
# importable from every migration.
import padel_tour.db.models

revision: str = "accounts"
down_revision: str | None = "d79a4a4829cb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UtcDateTime = padel_tour.db.models.UtcDateTime

PROVIDER_TELEGRAM = "telegram"

FK_GROUP_OWNER = "fk_groups_owner_account"
FK_PLAYER_ACCOUNT = "fk_players_account"
FK_TOURNAMENT_ORGANISER = "fk_tournaments_organiser_account"


def _create_tables() -> None:
    op.create_table(
        "accounts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("display_name", sa.String(length=100), nullable=True),
        sa.Column(
            "created_at",
            UtcDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "identities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=320), nullable=False),
        sa.Column(
            "created_at",
            UtcDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_identity_external", "identities", ["provider", "external_id"], unique=True)
    op.create_index("uq_identity_provider", "identities", ["account_id", "provider"], unique=True)

    op.create_table(
        "sessions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("account_id", sa.Uuid(), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", UtcDateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            UtcDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_session_token", "sessions", ["token_hash"], unique=True)

    op.create_table(
        "magic_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", UtcDateTime(timezone=True), nullable=False),
        sa.Column("used_at", UtcDateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            UtcDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_magic_token", "magic_links", ["token_hash"], unique=True)

    op.create_table(
        "invites",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("player_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_account_id", sa.Uuid(), nullable=True),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", UtcDateTime(timezone=True), nullable=False),
        sa.Column("used_at", UtcDateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            UtcDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["created_by_account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["player_id"], ["players.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("uq_invite_token", "invites", ["token_hash"], unique=True)

    op.create_table(
        "group_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("group_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=20), nullable=False),
        sa.Column("external_id", sa.String(length=320), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["groups.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_group_link_external", "group_links", ["provider", "external_id"], unique=True
    )
    op.create_index("uq_group_link_provider", "group_links", ["group_id", "provider"], unique=True)


def _add_columns() -> None:
    op.add_column("groups", sa.Column("owner_account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        FK_GROUP_OWNER, "groups", "accounts", ["owner_account_id"], ["id"], ondelete="SET NULL"
    )

    op.add_column("players", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        FK_PLAYER_ACCOUNT, "players", "accounts", ["account_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index(
        "uq_players_group_account",
        "players",
        ["group_id", "account_id"],
        unique=True,
        sqlite_where=sa.text("account_id IS NOT NULL"),
        postgresql_where=sa.text("account_id IS NOT NULL"),
    )

    op.add_column("tournaments", sa.Column("organiser_account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        FK_TOURNAMENT_ORGANISER,
        "tournaments",
        "accounts",
        ["organiser_account_id"],
        ["id"],
        ondelete="SET NULL",
    )


def _move_data_in() -> None:
    """Carry the Telegram bindings into the new shape.

    Done in Python rather than SQL so it reads the same on SQLite and Postgres — neither
    `gen_random_uuid()` nor `uuid_generate_v4()` exists on both.
    """
    connection = op.get_bind()

    # Every chat a group was bound to becomes a link.
    chats = connection.execute(
        sa.text("SELECT id, telegram_chat_id FROM groups WHERE telegram_chat_id IS NOT NULL")
    ).all()
    for group_id, chat_id in chats:
        connection.execute(
            sa.text("""
                INSERT INTO group_links (id, group_id, provider, external_id)
                VALUES (:id, :group_id, :provider, :external_id)
            """),
            {
                "id": uuid.uuid7(),
                "group_id": group_id,
                "provider": PROVIDER_TELEGRAM,
                "external_id": str(chat_id),
            },
        )

    # Every organiser known only by a Telegram id becomes an account with an identity.
    organisers = (
        connection.execute(
            sa.text("""
            SELECT DISTINCT organiser_telegram_id FROM tournaments
            WHERE organiser_telegram_id IS NOT NULL
        """)
        )
        .scalars()
        .all()
    )

    for telegram_id in organisers:
        account_id = uuid.uuid7()
        connection.execute(
            sa.text("INSERT INTO accounts (id) VALUES (:id)"),
            {"id": account_id},
        )
        connection.execute(
            sa.text("""
                INSERT INTO identities (id, account_id, provider, external_id)
                VALUES (:id, :account_id, :provider, :external_id)
            """),
            {
                "id": uuid.uuid7(),
                "account_id": account_id,
                "provider": PROVIDER_TELEGRAM,
                "external_id": str(telegram_id),
            },
        )
        connection.execute(
            sa.text("""
                UPDATE tournaments SET organiser_account_id = :account_id
                WHERE organiser_telegram_id = :telegram_id
            """),
            {"account_id": account_id, "telegram_id": telegram_id},
        )


def _move_data_out() -> None:
    """Put the Telegram bindings back where downgrade expects them."""
    connection = op.get_bind()

    links = connection.execute(
        sa.text("SELECT group_id, external_id FROM group_links WHERE provider = :provider"),
        {"provider": PROVIDER_TELEGRAM},
    ).all()
    for group_id, external_id in links:
        connection.execute(
            sa.text("UPDATE groups SET telegram_chat_id = :chat WHERE id = :id"),
            {"chat": int(external_id), "id": group_id},
        )

    organisers = connection.execute(
        sa.text("""
            SELECT t.id, i.external_id
            FROM tournaments t
            JOIN identities i ON i.account_id = t.organiser_account_id
            WHERE i.provider = :provider
        """),
        {"provider": PROVIDER_TELEGRAM},
    ).all()
    for tournament_id, external_id in organisers:
        connection.execute(
            sa.text("UPDATE tournaments SET organiser_telegram_id = :tg WHERE id = :id"),
            {"tg": int(external_id), "id": tournament_id},
        )


def upgrade() -> None:
    _create_tables()
    _add_columns()
    _move_data_in()

    # Only now that the data has moved.
    with op.batch_alter_table("groups") as batch:
        batch.drop_column("telegram_chat_id")
    with op.batch_alter_table("tournaments") as batch:
        batch.drop_column("organiser_telegram_id")


def downgrade() -> None:
    op.add_column("groups", sa.Column("telegram_chat_id", sa.BigInteger(), nullable=True))
    op.add_column("tournaments", sa.Column("organiser_telegram_id", sa.BigInteger(), nullable=True))
    _move_data_out()

    op.drop_constraint(FK_TOURNAMENT_ORGANISER, "tournaments", type_="foreignkey")
    op.drop_column("tournaments", "organiser_account_id")

    op.drop_index("uq_players_group_account", table_name="players")
    op.drop_constraint(FK_PLAYER_ACCOUNT, "players", type_="foreignkey")
    op.drop_column("players", "account_id")

    op.drop_constraint(FK_GROUP_OWNER, "groups", type_="foreignkey")
    op.drop_column("groups", "owner_account_id")

    op.drop_index("uq_group_link_provider", table_name="group_links")
    op.drop_index("uq_group_link_external", table_name="group_links")
    op.drop_table("group_links")
    op.drop_index("uq_invite_token", table_name="invites")
    op.drop_table("invites")
    op.drop_index("uq_magic_token", table_name="magic_links")
    op.drop_table("magic_links")
    op.drop_index("uq_session_token", table_name="sessions")
    op.drop_table("sessions")
    op.drop_index("uq_identity_provider", table_name="identities")
    op.drop_index("uq_identity_external", table_name="identities")
    op.drop_table("identities")
    op.drop_table("accounts")
