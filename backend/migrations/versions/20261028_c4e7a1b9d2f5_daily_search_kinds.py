"""preferences.daily_search_kinds

Revision ID: c4e7a1b9d2f5
Revises: b8d2f4a6c1e3
Create Date: 2026-10-28 18:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c4e7a1b9d2f5"
down_revision: str | None = "b8d2f4a6c1e3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "preferences",
        sa.Column(
            "daily_search_kinds",
            postgresql.ARRAY(sa.Text()),
            server_default="{jobs}",
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("preferences", "daily_search_kinds")
