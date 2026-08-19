"""Add the achievement engine foundation.

Revision ID: 0011_achievement_engine
Revises: 0010_user_moderation
"""
from alembic import op
import sqlalchemy as sa

revision = "0011_achievement_engine"
down_revision = "0010_user_moderation"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "achievement_definitions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(96), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(48), nullable=False),
        sa.Column("icon", sa.String(255), nullable=True),
        sa.Column("achievement_type", sa.String(24), nullable=False, server_default="SINGLE"),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="PUBLIC"),
        sa.Column("repeatable", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("criteria", sa.JSON(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("achievement_type in ('SINGLE','TIERED','REPEATABLE','STATUS')", name="achievement_definition_type_valid"),
        sa.CheckConstraint("visibility in ('PUBLIC','HIDDEN','SECRET')", name="achievement_definition_visibility_valid"),
        sa.CheckConstraint("sort_order >= 0", name="achievement_definition_sort_nonnegative"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key"),
    )
    op.create_index("ix_achievement_definitions_category", "achievement_definitions", ["category"])
    op.create_index("ix_achievement_definitions_enabled", "achievement_definitions", ["enabled"])
    op.create_index("ix_achievement_definition_category_sort", "achievement_definitions", ["category", "sort_order"])

    op.create_table(
        "achievement_tiers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("achievement_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(48), nullable=False),
        sa.Column("name", sa.String(96), nullable=False),
        sa.Column("threshold", sa.Numeric(20, 6), nullable=True),
        sa.Column("criteria", sa.JSON(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("icon", sa.String(255), nullable=True),
        sa.CheckConstraint("sort_order >= 0", name="achievement_tier_sort_nonnegative"),
        sa.CheckConstraint("threshold is null or threshold >= 0", name="achievement_tier_threshold_nonnegative"),
        sa.ForeignKeyConstraint(["achievement_id"], ["achievement_definitions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("achievement_id", "key", name="uq_achievement_tier_key"),
        sa.UniqueConstraint("achievement_id", "sort_order", name="uq_achievement_tier_sort"),
    )
    op.create_index("ix_achievement_tiers_achievement_id", "achievement_tiers", ["achievement_id"])

    op.create_table(
        "achievement_metrics",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("metric_key", sa.String(96), nullable=False),
        sa.Column("value", sa.Numeric(20, 6), nullable=False, server_default="0"),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "metric_key"),
    )
    op.create_index("ix_achievement_metric_key_value", "achievement_metrics", ["metric_key", "value"])

    op.create_table(
        "achievement_event_receipts",
        sa.Column("event_key", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(96), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("event_key"),
    )
    op.create_index("ix_achievement_event_receipts_user_id", "achievement_event_receipts", ["user_id"])
    op.create_index("ix_achievement_event_receipts_event_type", "achievement_event_receipts", ["event_type"])

    op.create_table(
        "user_achievement_states",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("achievement_id", sa.Uuid(), nullable=False),
        sa.Column("current_tier_id", sa.Uuid(), nullable=True),
        sa.Column("progress", sa.JSON(), nullable=False),
        sa.Column("earned_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("first_earned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_earned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("earned_count >= 0", name="user_achievement_state_count_nonnegative"),
        sa.ForeignKeyConstraint(["achievement_id"], ["achievement_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["current_tier_id"], ["achievement_tiers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "achievement_id"),
    )
    op.create_index("ix_user_achievement_states_current_tier_id", "user_achievement_states", ["current_tier_id"])
    op.create_index("ix_user_achievement_state_user_updated", "user_achievement_states", ["user_id", "updated_at"])

    op.create_table(
        "user_achievement_awards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("award_key", sa.String(255), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("achievement_id", sa.Uuid(), nullable=False),
        sa.Column("tier_id", sa.Uuid(), nullable=True),
        sa.Column("source_event_key", sa.String(255), nullable=True),
        sa.Column("period_key", sa.String(64), nullable=True),
        sa.Column("scope_type", sa.String(32), nullable=True),
        sa.Column("scope_key", sa.String(128), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("earned_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoke_reason", sa.Text(), nullable=True),
        sa.Column("revoked_by_admin_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["achievement_id"], ["achievement_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["revoked_by_admin_id"], ["profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["tier_id"], ["achievement_tiers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("award_key"),
    )
    op.create_index("ix_user_achievement_awards_user_id", "user_achievement_awards", ["user_id"])
    op.create_index("ix_user_achievement_awards_achievement_id", "user_achievement_awards", ["achievement_id"])
    op.create_index("ix_user_achievement_awards_source_event_key", "user_achievement_awards", ["source_event_key"])
    op.create_index("ix_user_achievement_awards_period_key", "user_achievement_awards", ["period_key"])
    op.create_index("ix_user_achievement_awards_scope_key", "user_achievement_awards", ["scope_key"])
    op.create_index("ix_user_achievement_award_user_earned", "user_achievement_awards", ["user_id", "earned_at"])
    op.create_index("ix_user_achievement_award_scope_period", "user_achievement_awards", ["scope_type", "scope_key", "period_key"])


def downgrade():
    op.drop_table("user_achievement_awards")
    op.drop_table("user_achievement_states")
    op.drop_table("achievement_event_receipts")
    op.drop_table("achievement_metrics")
    op.drop_table("achievement_tiers")
    op.drop_table("achievement_definitions")
