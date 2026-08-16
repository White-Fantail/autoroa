"""Persist saturated station catalog cells.

Revision ID: 0005_station_catalog_saturation
Revises: 0004_ocr_jobs
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_station_catalog_saturation"
down_revision = "0004_ocr_jobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "station_catalog_saturated_cells",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("latitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("longitude", sa.Numeric(9, 6), nullable=False),
        sa.Column("radius_km", sa.Numeric(7, 3), nullable=False),
        sa.Column("density", sa.String(), nullable=False),
        sa.Column("refinement_depth", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "latitude", "longitude", "radius_km", "refinement_depth",
            name="uq_station_catalog_saturated_cell",
        ),
    )
    op.create_index(
        "ix_station_catalog_saturated_last_seen",
        "station_catalog_saturated_cells",
        ["last_seen_at"],
    )


def downgrade():
    op.drop_index("ix_station_catalog_saturated_last_seen", table_name="station_catalog_saturated_cells")
    op.drop_table("station_catalog_saturated_cells")
