"""Add gmail_notifications table for persisted Gmail inbox alerts.

Revision ID: 20261024_0008
Revises: 20261020_0007
Create Date: 2026-10-24 22:15:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261024_0008"
down_revision: Union[str, None] = "20261020_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "gmail_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("gmail_message_id", sa.String(length=255), nullable=False),
        sa.Column("gmail_thread_id", sa.String(length=255), nullable=True),
        sa.Column("sender", sa.String(length=255), nullable=True),
        sa.Column("subject", sa.String(length=500), nullable=True),
        sa.Column("snippet", sa.String(length=500), nullable=True),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "gmail_message_id", name="uq_gmail_notifications_user_message"),
    )
    op.create_index("ix_gmail_notifications_user_id", "gmail_notifications", ["user_id"])
    op.create_index("ix_gmail_notifications_user_created", "gmail_notifications", ["user_id", "created_at"])
    op.create_index("ix_gmail_notifications_user_unread", "gmail_notifications", ["user_id", "is_read"])


def downgrade() -> None:
    op.drop_index("ix_gmail_notifications_user_unread", table_name="gmail_notifications")
    op.drop_index("ix_gmail_notifications_user_created", table_name="gmail_notifications")
    op.drop_index("ix_gmail_notifications_user_id", table_name="gmail_notifications")
    op.drop_table("gmail_notifications")
