"""Link admin price observations to their source photo.

Revision ID: 0003
Revises: 0002
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("fuel_price_observations") as batch:
        batch.add_column(sa.Column("media_asset_id", sa.Uuid(), nullable=True))
        batch.create_foreign_key("fk_observation_media", "media_assets", ["media_asset_id"], ["id"], ondelete="SET NULL")
        batch.create_unique_constraint("uq_observation_media_fuel", ["media_asset_id", "fuel_type"])
    op.create_index("ix_fuel_price_observations_media_asset_id", "fuel_price_observations", ["media_asset_id"])


def downgrade() -> None:
    op.drop_index("ix_fuel_price_observations_media_asset_id", table_name="fuel_price_observations")
    with op.batch_alter_table("fuel_price_observations") as batch:
        batch.drop_constraint("uq_observation_media_fuel", type_="unique")
        batch.drop_constraint("fk_observation_media", type_="foreignkey")
        batch.drop_column("media_asset_id")
