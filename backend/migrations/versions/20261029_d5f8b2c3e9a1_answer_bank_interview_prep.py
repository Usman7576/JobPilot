"""users.answer_bank, draft_kind interview_prep

Revision ID: d5f8b2c3e9a1
Revises: c4e7a1b9d2f5
Create Date: 2026-10-29 10:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d5f8b2c3e9a1"
down_revision: str | None = "c4e7a1b9d2f5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("answer_bank", sa.LargeBinary(), nullable=True))
    op.execute("ALTER TYPE draft_kind ADD VALUE IF NOT EXISTS 'interview_prep'")


def downgrade() -> None:
    # Postgres can't drop an enum value; delete the drafts that use it instead.
    op.execute("DELETE FROM application_drafts WHERE kind = 'interview_prep'")
    op.drop_column("users", "answer_bank")
