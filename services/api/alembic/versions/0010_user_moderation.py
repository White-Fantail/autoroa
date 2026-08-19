"""Add application-level user moderation.

Revision ID: 0010_user_moderation
Revises: 0009_station_issue_reports
"""
from alembic import op
import sqlalchemy as sa

revision = "0010_user_moderation"
down_revision = "0009_station_issue_reports"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_moderation_states",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="ACTIVE"),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("moderated_by_admin_id", sa.Uuid(), nullable=True),
        sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status in ('ACTIVE','SUSPENDED','BANNED')",
            name="user_moderation_state_status_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["moderated_by_admin_id"], ["profiles.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )
    op.create_index(
        "ix_user_moderation_states_moderated_by_admin_id",
        "user_moderation_states",
        ["moderated_by_admin_id"],
    )
    op.create_index(
        "ix_user_moderation_states_status",
        "user_moderation_states",
        ["status"],
    )

    op.create_table(
        "user_moderation_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("previous_status", sa.String(20), nullable=False),
        sa.Column("new_status", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "previous_status in ('ACTIVE','SUSPENDED','BANNED')",
            name="user_moderation_event_previous_status_valid",
        ),
        sa.CheckConstraint(
            "new_status in ('ACTIVE','SUSPENDED','BANNED')",
            name="user_moderation_event_new_status_valid",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["admin_user_id"], ["profiles.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_user_moderation_events_user_id",
        "user_moderation_events",
        ["user_id"],
    )
    op.create_index(
        "ix_user_moderation_events_new_status",
        "user_moderation_events",
        ["new_status"],
    )
    op.create_index(
        "ix_user_moderation_events_admin_user_id",
        "user_moderation_events",
        ["admin_user_id"],
    )
    op.create_index(
        "ix_user_moderation_events_user_created",
        "user_moderation_events",
        ["user_id", "created_at"],
    )


def downgrade():
    op.drop_table("user_moderation_events")
    op.drop_table("user_moderation_states")
