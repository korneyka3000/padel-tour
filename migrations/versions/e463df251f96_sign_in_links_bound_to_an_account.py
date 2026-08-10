"""Sign-in links bound to an account

Lets the bot hand somebody a way into the web when it already knows who they are, with no
mail server in the way.

**Migrate before deploying.** Additive, but the model maps the column, so SQLAlchemy names
it in every read of a magic link — see Р-039.

Autogenerate left the foreign key unnamed, which makes ``drop_constraint(None, ...)`` in the
downgrade a runtime error on Postgres. Named here, so the migration reverses.

Revision ID: e463df251f96
Revises: 9131dafc6930
Create Date: 2026-08-11 00:53:34.264982
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e463df251f96"
down_revision: str | None = "9131dafc6930"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FK = "fk_magic_links_account_id"


def upgrade() -> None:
    op.add_column("magic_links", sa.Column("account_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(FK, "magic_links", "accounts", ["account_id"], ["id"], ondelete="CASCADE")


def downgrade() -> None:
    op.drop_constraint(FK, "magic_links", type_="foreignkey")
    op.drop_column("magic_links", "account_id")
