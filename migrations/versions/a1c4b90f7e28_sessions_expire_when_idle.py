"""Sessions expire when idle

Adds the second deadline. Until now a session lived thirty days from the sign-in and nothing
shortened that, so a cookie copied off an unlocked laptop was good for a month whether or not
its owner ever came back. ``last_used_at`` is what makes "nobody has touched this in two
weeks" answerable.

**Migrate before deploying.** Additive, but the model maps the column, so SQLAlchemy names it
in every read of a session — which is every authenticated request. Deploying first is the
shape of Р-039 and Р-043: 500 on the column that is not there yet.

Existing rows get ``now()`` rather than ``created_at``. It is the generous reading — everyone
already signed in gets a fresh two weeks instead of being logged out by a migration — and
picking the deadline over the audit trail is the right way round for a column whose only job
is deciding when to stop trusting a token.

Indexed because the purge on sign-in filters on it, alongside ``expires_at``.

Revision ID: a1c4b90f7e28
Revises: e463df251f96
Create Date: 2026-08-11 09:58:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import padel_tour.db.models

UtcDateTime = padel_tour.db.models.UtcDateTime

revision: str = "a1c4b90f7e28"
down_revision: str | None = "e463df251f96"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX = "ix_sessions_last_used_at"


def upgrade() -> None:
    op.add_column(
        "sessions",
        sa.Column(
            "last_used_at",
            UtcDateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(INDEX, "sessions", ["last_used_at"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name="sessions")
    op.drop_column("sessions", "last_used_at")
