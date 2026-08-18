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
    with op.batch_alter_table("media_assets") as batch:
        batch.alter_column("user_id", nullable=True)
    with op.batch_alter_table("ocr_jobs") as batch:
        batch.alter_column("user_id", nullable=True)


def downgrade():
    # Anonymous rows cannot satisfy the original ownership requirement. Remove
    # anonymous community observations and OCR/media rows before restoring it.
    op.execute(
        "DELETE FROM fuel_price_observations WHERE media_asset_id IN "
        "(SELECT id FROM media_assets WHERE user_id IS NULL)"
    )
    op.execute("DELETE FROM ocr_jobs WHERE user_id IS NULL")
    op.execute("DELETE FROM media_assets WHERE user_id IS NULL")
    with op.batch_alter_table("ocr_jobs") as batch:
        batch.alter_column("user_id", nullable=False)
    with op.batch_alter_table("media_assets") as batch:
        batch.alter_column("user_id", nullable=False)
