"""Link multiple Supabase auth identities to one Autoroa profile.

Revision ID: 0015_auth_identities
Revises: 0014_profile_achievement_experience
"""
from alembic import op
import sqlalchemy as sa

revision = "0015_auth_identities"
down_revision = "0014_profile_achievement_experience"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "profile_auth_identities",
        sa.Column("auth_user_id", sa.String(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(40), nullable=True),
        sa.Column("email", sa.String(320), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["profile_id"], ["profiles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("auth_user_id"),
    )
    op.create_index("ix_profile_auth_identities_profile_id", "profile_auth_identities", ["profile_id"])
    op.create_index("ix_profile_auth_identities_email", "profile_auth_identities", ["email"])
    op.execute(
        """
        INSERT INTO profile_auth_identities (auth_user_id, profile_id, provider, email, created_at, updated_at)
        SELECT auth_user_id, id, NULL, NULL, created_at, updated_at
        FROM profiles
        WHERE deleted_at IS NULL
        """
    )


def downgrade():
    op.drop_index("ix_profile_auth_identities_email", table_name="profile_auth_identities")
    op.drop_index("ix_profile_auth_identities_profile_id", table_name="profile_auth_identities")
    op.drop_table("profile_auth_identities")
