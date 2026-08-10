"""Remember the chart message

**Migrate before deploying.** This one is additive, and I wrote here that the order
therefore did not matter. It does. Additive means *old* code survives the new schema; it
says nothing about new code surviving the old one, and the model maps this column, so
SQLAlchemy selects it on every read of a tournament. Pushing first took production to 500
on every tournament route until the migration caught up — see Р-039.

The rule, stated properly: a migration that adds something the new code needs goes first;
one that removes something the old code still uses goes second; only a change neither side
depends on is free to go either way.

Revision ID: 9131dafc6930
Revises: accounts
Create Date: 2026-08-11 00:02:46.447854
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "9131dafc6930"
down_revision: str | None = "accounts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("tournaments", sa.Column("chart_message_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("tournaments", "chart_message_id")
