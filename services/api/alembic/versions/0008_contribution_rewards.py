"""Add fuel-level contribution results and immutable point ledger.

Revision ID: 0008_contribution_rewards
Revises: 0007_user_price_board
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0008_contribution_rewards"
down_revision = "0007_user_price_board"
branch_labels = None
depends_on = None


def upgrade():
    fuel_type = postgresql.ENUM(
        "PETROL_91", "PETROL_95", "PETROL_98", "DIESEL", "OTHER",
        name="fueltype", create_type=False,
    )
    op.create_table(
        "submission_fuel_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("station_id", sa.Uuid(), nullable=False),
        sa.Column("fuel_type", fuel_type, nullable=False),
        sa.Column("previous_price", sa.Numeric(8, 4), nullable=True),
        sa.Column("submitted_price", sa.Numeric(8, 4), nullable=False),
        sa.Column("final_price", sa.Numeric(8, 4), nullable=True),
        sa.Column("result", sa.String(24), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("observation_id", sa.Uuid(), nullable=True),
        sa.Column("previous_observation_id", sa.Uuid(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("points in (0, 1)", name="submission_fuel_result_points"),
        sa.ForeignKeyConstraint(["submission_id"], ["community_price_board_submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["station_id"], ["fuel_stations.id"]),
        sa.ForeignKeyConstraint(["observation_id"], ["fuel_price_observations.id"]),
        sa.ForeignKeyConstraint(["previous_observation_id"], ["fuel_price_observations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "fuel_type", name="uq_submission_fuel_result"),
    )
    op.create_index("ix_submission_fuel_results_submission_id", "submission_fuel_results", ["submission_id"])
    op.create_index("ix_submission_fuel_results_station_id", "submission_fuel_results", ["station_id"])
    op.create_index("ix_submission_fuel_result_station_fuel", "submission_fuel_results", ["station_id", "fuel_type"])

    op.create_table(
        "point_transactions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("submission_id", sa.Uuid(), nullable=False),
        sa.Column("station_id", sa.Uuid(), nullable=False),
        sa.Column("fuel_type", fuel_type, nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("reason", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("points <> 0", name="point_transaction_nonzero"),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["submission_id"], ["community_price_board_submissions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["station_id"], ["fuel_stations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("submission_id", "fuel_type", "reason", name="uq_point_transaction_reason"),
    )
    op.create_index("ix_point_transactions_user_id", "point_transactions", ["user_id"])
    op.create_index("ix_point_transactions_submission_id", "point_transactions", ["submission_id"])
    op.create_index("ix_point_transactions_station_id", "point_transactions", ["station_id"])
    op.create_index("ix_point_transaction_station_created", "point_transactions", ["station_id", "created_at"])
    op.create_index("ix_point_transaction_user_created", "point_transactions", ["user_id", "created_at"])


def downgrade():
    op.drop_table("point_transactions")
    op.drop_table("submission_fuel_results")
