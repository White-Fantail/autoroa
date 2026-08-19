"""Authenticated community price-board submissions.

Revision ID: 0007_user_price_board
Revises: 0006_anonymous_price_board_ocr
"""

from alembic import op
import sqlalchemy as sa

revision = "0007_user_price_board"
down_revision = "0006_anonymous_price_board_ocr"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "community_price_board_submissions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("ocr_job_id", sa.Uuid(), nullable=False),
        sa.Column("selected_station_id", sa.Uuid(), nullable=False),
        sa.Column("detected_station_id", sa.Uuid(), nullable=True),
        sa.Column("photo_latitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("photo_longitude", sa.Numeric(9, 6), nullable=True),
        sa.Column("selected_station_distance_km", sa.Numeric(8, 3), nullable=True),
        sa.Column("location_status", sa.String(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["ocr_job_id"], ["ocr_jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["selected_station_id"], ["fuel_stations.id"]),
        sa.ForeignKeyConstraint(["detected_station_id"], ["fuel_stations.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("ocr_job_id"),
    )
    op.create_index("ix_community_price_board_submission_user_created", "community_price_board_submissions", ["user_id", "created_at"])
    op.create_index("ix_community_price_board_submission_station_created", "community_price_board_submissions", ["selected_station_id", "created_at"])


def downgrade():
    op.drop_index("ix_community_price_board_submission_station_created", table_name="community_price_board_submissions")
    op.drop_index("ix_community_price_board_submission_user_created", table_name="community_price_board_submissions")
    op.drop_table("community_price_board_submissions")
