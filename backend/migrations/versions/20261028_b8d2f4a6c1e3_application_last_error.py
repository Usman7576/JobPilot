"""application last_error

Revision ID: b8d2f4a6c1e3
Revises: a3c1e5d2b7f4
Create Date: 2026-10-28 00:30:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b8d2f4a6c1e3"
down_revision: str | None = "a3c1e5d2b7f4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("applications", sa.Column("last_error", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("applications", "last_error")
