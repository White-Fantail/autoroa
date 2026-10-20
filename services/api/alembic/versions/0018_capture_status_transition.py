"""Normalize existing Quick Capture states without replacing deployed schema.

Revision ID: 0018_capture_status_transition
Revises: 0017_quick_captures
"""
from alembic import op
import sqlalchemy as sa

revision = "0018_capture_status_transition"
down_revision = "0017_quick_captures"
branch_labels = None
depends_on = None


def upgrade():
    # Existing captures created before the camera redesign remain accessible.
    op.execute(sa.text(
        "UPDATE quick_captures SET status='CONFIRMED' WHERE status='COMPLETED'"
    ))
    op.execute(sa.text(
        "UPDATE quick_captures SET status='REVIEW_REQUIRED' WHERE status='NEEDS_REVIEW'"
    ))


def downgrade():
    op.execute(sa.text(
        "UPDATE quick_captures SET status='COMPLETED' WHERE status='CONFIRMED'"
    ))
    op.execute(sa.text(
        "UPDATE quick_captures SET status='NEEDS_REVIEW' WHERE status='REVIEW_REQUIRED'"
    ))
