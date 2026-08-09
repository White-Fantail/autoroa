"""Ensure the rate-limit table exists for legacy databases.

Revision ID: 0001_rate_limits
Revises: 0001
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0001_rate_limits"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if not inspector.has_table("rate_limits"):
        op.create_table(
            "rate_limits",
            sa.Column("key", sa.String(), nullable=False),
            sa.Column("window_started_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("count", sa.Integer(), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )


def downgrade() -> None:
    # Revision 0001 also owns this table for databases created through Alembic.
    pass
