"""Add durable OCR jobs.

Revision ID: 0004_ocr_jobs
Revises: 0003
"""
from alembic import op
import sqlalchemy as sa

revision="0004_ocr_jobs"
down_revision="0003"
branch_labels=None
depends_on=None

def upgrade():
    # Claim tokens fence stale workers from committing after a job is reclaimed.
    op.create_table("ocr_jobs",sa.Column("id",sa.Uuid(),primary_key=True),sa.Column("user_id",sa.Uuid(),nullable=False),sa.Column("kind",sa.Enum("RECEIPT","ODOMETER","PRICE_BOARD",name="ocrjobkind"),nullable=False),sa.Column("resource_id",sa.Uuid(),nullable=False),sa.Column("station_id",sa.Uuid(),nullable=True),sa.Column("media_asset_id",sa.Uuid(),nullable=False),sa.Column("status",sa.Enum("UPLOADED","PROCESSING","REVIEW_REQUIRED","READY","FAILED","CONFIRMED",name="status",create_type=False),nullable=False),sa.Column("result_json",sa.JSON()),sa.Column("confidence",sa.Numeric(4,3)),sa.Column("requires_confirmation",sa.Boolean(),nullable=False),sa.Column("applied_at",sa.DateTime(timezone=True)),sa.Column("error_message",sa.String()),sa.Column("created_at",sa.DateTime(timezone=True),nullable=False),sa.Column("started_at",sa.DateTime(timezone=True)),sa.Column("completed_at",sa.DateTime(timezone=True)),sa.CheckConstraint("confidence is null or confidence between 0 and 1",name="ocr_job_confidence_range"),sa.ForeignKeyConstraint(["user_id"],["profiles.id"],ondelete="CASCADE"),sa.ForeignKeyConstraint(["station_id"],["fuel_stations.id"]),sa.ForeignKeyConstraint(["media_asset_id","user_id"],["media_assets.id","media_assets.user_id"],ondelete="CASCADE",name="fk_ocr_job_media_owner"))
    op.create_index("ix_ocr_jobs_user_id","ocr_jobs",["user_id"]);op.create_index("ix_ocr_jobs_resource_id","ocr_jobs",["resource_id"]);op.create_index("ix_ocr_jobs_status","ocr_jobs",["status"]);op.create_index("ix_ocr_jobs_owner_created","ocr_jobs",["user_id","created_at"])
    op.create_index("uq_ocr_job_active_resource","ocr_jobs",["user_id","kind","resource_id"],unique=True,postgresql_where=sa.text("status in ('UPLOADED','PROCESSING')"),sqlite_where=sa.text("status in ('UPLOADED','PROCESSING')"))

    op.add_column("ocr_jobs",sa.Column("claim_token",sa.Uuid(),nullable=True))

def downgrade():
    op.drop_table("ocr_jobs")
    if op.get_bind().dialect.name=="postgresql":op.execute("DROP TYPE ocrjobkind")
