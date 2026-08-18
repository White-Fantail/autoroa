"""Allow anonymous community price-board OCR jobs.

Revision ID: 0006_anonymous_price_board_ocr
Revises: 0005_station_catalog_saturation
"""

from alembic import op

revision = "0006_anonymous_price_board_ocr"
down_revision = "0005_station_catalog_saturation"
branch_labels = None
depends_on = None


def upgrade():
    op.alter_column("media_assets", "user_id", existing_type=None, nullable=True)
    op.alter_column("ocr_jobs", "user_id", existing_type=None, nullable=True)


def downgrade():
    # Anonymous rows cannot satisfy the original ownership requirement. Remove
    # only anonymous community OCR records before restoring NOT NULL.
    op.execute("DELETE FROM ocr_jobs WHERE user_id IS NULL")
    op.execute(
        "DELETE FROM media_assets WHERE user_id IS NULL "
        "AND id NOT IN (SELECT media_asset_id FROM fuel_price_observations WHERE media_asset_id IS NOT NULL)"
    )
    op.alter_column("ocr_jobs", "user_id", existing_type=None, nullable=False)
    op.alter_column("media_assets", "user_id", existing_type=None, nullable=False)
