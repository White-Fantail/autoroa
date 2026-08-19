"""Add achievement profile preferences and seen receipts.

Revision ID: 0014_profile_achievement_experience
Revises: 0013_regional_achievements
"""
from alembic import op
import sqlalchemy as sa

revision = "0014_profile_achievement_experience"
down_revision = "0013_regional_achievements"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_featured_achievements",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("slot", sa.Integer(), nullable=False),
        sa.Column("achievement_id", sa.Uuid(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["achievement_id"], ["achievement_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "slot"),
        sa.UniqueConstraint("user_id", "achievement_id", name="uq_user_featured_achievement"),
    )
    op.create_index("ix_user_featured_achievements_achievement_id", "user_featured_achievements", ["achievement_id"])
    op.create_table(
        "user_achievement_seen",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("award_id", sa.Uuid(), nullable=False),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["award_id"], ["user_achievement_awards.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "award_id"),
    )
    op.create_index("ix_user_achievement_seen_user_seen", "user_achievement_seen", ["user_id", "seen_at"])
    # Existing achievements predate the celebration feed. Mark them seen so
    # deploying this feature does not replay a long backlog of old unlocks.
    op.execute(
        "INSERT INTO user_achievement_seen (user_id, award_id, seen_at) "
        "SELECT user_id, id, CURRENT_TIMESTAMP FROM user_achievement_awards"
    )


def downgrade():
    op.drop_table("user_achievement_seen")
    op.drop_table("user_featured_achievements")
