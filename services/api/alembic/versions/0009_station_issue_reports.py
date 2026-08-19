"""Add station issue reports.

Revision ID: 0009_station_issue_reports
Revises: 0008_contribution_rewards
"""
from alembic import op
import sqlalchemy as sa

revision = "0009_station_issue_reports"
down_revision = "0008_contribution_rewards"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "station_issue_reports",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("station_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["station_id"], ["fuel_stations.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_station_issue_reports_station_id", "station_issue_reports", ["station_id"])
    op.create_index("ix_station_issue_reports_user_id", "station_issue_reports", ["user_id"])
    op.create_index("ix_station_issue_reports_status", "station_issue_reports", ["status"])
    op.create_index("ix_station_issue_report_station_created", "station_issue_reports", ["station_id", "created_at"])
    op.create_index("ix_station_issue_report_status_created", "station_issue_reports", ["status", "created_at"])


def downgrade():
    op.drop_table("station_issue_reports")
