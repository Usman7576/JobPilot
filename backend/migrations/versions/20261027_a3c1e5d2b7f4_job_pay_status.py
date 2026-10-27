"""job pay status (paid / unpaid / unknown)

Revision ID: a3c1e5d2b7f4
Revises: 70c595fb8365
Create Date: 2026-10-27 22:00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "a3c1e5d2b7f4"
down_revision: str | None = "70c595fb8365"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

pay_status = postgresql.ENUM("paid", "unpaid", "unknown", name="pay_status", create_type=False)


def upgrade() -> None:
    pay_status.create(op.get_bind(), checkfirst=True)
    op.add_column(
        "jobs",
        sa.Column("pay_status", pay_status, server_default="unknown", nullable=False),
    )
    # Existing jobs with a salary are paid; the rest are labelled when sources see them again.
    op.execute(
        "UPDATE jobs SET pay_status = 'paid' "
        "WHERE salary_min IS NOT NULL OR salary_max IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_column("jobs", "pay_status")
    pay_status.drop(op.get_bind(), checkfirst=True)
