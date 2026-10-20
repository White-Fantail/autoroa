"""Add idempotent, user-owned capture sessions for hands-off fuel recording.

Revision ID: 0017_quick_captures
Revises: 0016_optional_fillup_odometer
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_quick_captures"
down_revision = "0016_optional_fillup_odometer"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "quick_captures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("client_token", sa.String(100), nullable=False),
        sa.Column("vehicle_id", sa.Uuid(), nullable=False),
        sa.Column("receipt_id", sa.Uuid(), nullable=False),
        sa.Column("odometer_reading_id", sa.Uuid(), nullable=True),
        sa.Column("fill_up_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("error_code", sa.String(80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["vehicle_id", "user_id"], ["vehicles.id", "vehicles.user_id"]),
        sa.ForeignKeyConstraint(["receipt_id"], ["receipts.id"]),
        sa.ForeignKeyConstraint(["odometer_reading_id"], ["odometer_readings.id"]),
        sa.ForeignKeyConstraint(["fill_up_id"], ["fill_ups.id"]),
        sa.UniqueConstraint("user_id", "client_token", name="uq_quick_capture_token"),
        sa.UniqueConstraint("receipt_id"),
        sa.UniqueConstraint("odometer_reading_id"),
        sa.UniqueConstraint("fill_up_id"),
    )
    op.create_index("ix_quick_captures_user_id", "quick_captures", ["user_id"])


def downgrade():
    op.drop_index("ix_quick_captures_user_id", table_name="quick_captures")
    op.drop_table("quick_captures")
