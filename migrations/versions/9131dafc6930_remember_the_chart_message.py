"""Remember the chart message

Additive and nullable, so the order of deploy and migration does not matter this time:
old code ignores a column it has never heard of. That was not true of the accounts
migration, which dropped two columns the running code still selected and cost twenty
minutes of production 500s — see Р-031.

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
