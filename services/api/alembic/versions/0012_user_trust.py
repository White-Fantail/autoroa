"""Add contributor trust state.

Revision ID: 0012_user_trust
Revises: 0011_achievement_engine
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_user_trust"
down_revision = "0011_achievement_engine"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_trust_states",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("evaluated_result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("accurate_result_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recent_sample_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("recent_accurate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lifetime_accuracy", sa.Numeric(6, 3), nullable=True),
        sa.Column("recent_accuracy", sa.Numeric(6, 3), nullable=True),
        sa.Column("trust_score", sa.Numeric(6, 3), nullable=False, server_default="0"),
        sa.Column("moderation_status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("is_trusted_contributor", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("auto_review_eligible", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("last_evaluated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("evaluated_result_count >= 0", name="user_trust_evaluated_nonnegative"),
        sa.CheckConstraint("accurate_result_count >= 0", name="user_trust_accurate_nonnegative"),
        sa.CheckConstraint("recent_sample_count >= 0", name="user_trust_recent_sample_nonnegative"),
        sa.CheckConstraint("recent_accurate_count >= 0", name="user_trust_recent_accurate_nonnegative"),
        sa.CheckConstraint("trust_score between 0 and 100", name="user_trust_score_range"),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index("ix_user_trust_states_is_trusted_contributor", "user_trust_states", ["is_trusted_contributor"])
    op.create_index("ix_user_trust_states_auto_review_eligible", "user_trust_states", ["auto_review_eligible"])
    op.create_index("ix_user_trust_state_score", "user_trust_states", ["trust_score"])


def downgrade():
    op.drop_table("user_trust_states")
