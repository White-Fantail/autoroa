"""Allow receipt-only fuel records without invented odometer values.

Revision ID: 0016_optional_fillup_odometer
Revises: 0015_auth_identities
"""
from alembic import op
import sqlalchemy as sa

revision = "0016_optional_fillup_odometer"
down_revision = "0015_auth_identities"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("fill_ups") as batch:
        batch.alter_column("odometer_km", existing_type=sa.Integer(), nullable=True)


def downgrade():
    connection = op.get_bind()
    missing = connection.execute(sa.text("SELECT count(*) FROM fill_ups WHERE odometer_km IS NULL")).scalar()
    if missing:
        raise RuntimeError("Cannot require odometer: receipt-only records exist")
    with op.batch_alter_table("fill_ups") as batch:
        batch.alter_column("odometer_km", existing_type=sa.Integer(), nullable=False)
