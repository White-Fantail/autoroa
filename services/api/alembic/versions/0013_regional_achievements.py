"""Add regional leaderboard finalization persistence.

Revision ID: 0013_regional_achievements
Revises: 0012_user_trust
"""
from alembic import op
import sqlalchemy as sa

revision = "0013_regional_achievements"
down_revision = "0012_user_trust"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "leaderboard_period_finalizations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("period_key", sa.String(7), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_key", sa.String(128), nullable=False),
        sa.Column("scope_label", sa.String(160), nullable=False),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finalized_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("participant_count", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["finalized_by_admin_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("period_key", "scope_type", "scope_key", name="uq_leaderboard_period_finalization_scope"),
    )
    op.create_index("ix_leaderboard_period_finalization_period", "leaderboard_period_finalizations", ["period_key"])


def downgrade():
    op.drop_table("leaderboard_period_finalizations")
