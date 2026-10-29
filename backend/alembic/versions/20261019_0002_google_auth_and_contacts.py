"""Add Google auth columns and OAuth connections and contacts tables.

Revision ID: 20261019_0002
Revises: 20261017_0001
Create Date: 2026-10-19 19:10:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261019_0002"
down_revision: Union[str, None] = "20261017_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update users table with batch_alter_table for SQLite and PostgreSQL compatibility
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.add_column(sa.Column("google_sub", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("avatar_url", sa.String(length=1024), nullable=True))
        batch_op.create_index("ix_users_google_sub", ["google_sub"], unique=True)

    # 2. oauth_connections table
    op.create_table(
        "oauth_connections",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("encrypted_refresh_token", sa.Text(), nullable=True),
        sa.Column("access_token", sa.Text(), nullable=True),
        sa.Column("token_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_scopes", sa.Text(), nullable=True),
        sa.Column("connection_status", sa.String(length=50), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "provider", name="uq_oauth_connections_user_provider"),
        sa.UniqueConstraint("provider", "provider_user_id", name="uq_oauth_connections_provider_uid"),
    )
    op.create_index("ix_oauth_connections_user_id", "oauth_connections", ["user_id"])
    op.create_index("ix_oauth_connections_provider_user_id", "oauth_connections", ["provider_user_id"])

    # 3. user_contacts table
    op.create_table(
        "user_contacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=False),
        sa.Column("contact_email_normalized", sa.String(length=255), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=True),
        sa.Column("google_resource_name", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "contact_email_normalized", name="uq_user_contacts_user_email"),
    )
    op.create_index("ix_user_contacts_user_id", "user_contacts", ["user_id"])
    op.create_index("ix_user_contacts_contact_email_normalized", "user_contacts", ["contact_email_normalized"])
    op.create_index("ix_user_contacts_user_email", "user_contacts", ["user_id", "contact_email_normalized"])


def downgrade() -> None:
    op.drop_table("user_contacts")
    op.drop_table("oauth_connections")
    with op.batch_alter_table("users", schema=None) as batch_op:
        batch_op.drop_index("ix_users_google_sub")
        batch_op.drop_column("avatar_url")
        batch_op.drop_column("google_sub")
