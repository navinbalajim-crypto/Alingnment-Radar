"""Add message attachments, message deletion, task reminders, and notifications.

Revision ID: 20261027_0009
Revises: 20261024_0008
Create Date: 2026-10-27 12:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261027_0009"
down_revision: Union[str, None] = "20261024_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Alter messages table for deletion and unsend
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("is_deleted_for_everyone", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("deleted_by_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key("fk_messages_deleted_by_id", "users", ["deleted_by_id"], ["id"], ondelete="SET NULL")

    # 2. Table: message_attachments
    op.create_table(
        "message_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("uploader_id", sa.Uuid(), nullable=True),
        sa.Column("original_filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=False),
        sa.Column("storage_path", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["uploader_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_message_attachments_conv", "message_attachments", ["conversation_id"])
    op.create_index("ix_message_attachments_msg", "message_attachments", ["message_id"])

    # 3. Table: user_message_deletions (Delete for me)
    op.create_table(
        "user_message_deletions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "message_id", name="uq_user_message_deletions"),
    )
    op.create_index("ix_user_message_deletions_user_msg", "user_message_deletions", ["user_id", "message_id"])

    # 4. Table: task_reminders
    op.create_table(
        "task_reminders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_id", sa.Uuid(), nullable=False),
        sa.Column("responsible_user_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("advance_reminder_minutes", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column("advance_scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=50), server_default="Asia/Kolkata", nullable=False),
        sa.Column("status", sa.String(length=30), server_default="pending", nullable=False),
        sa.Column("advance_delivered", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("due_delivered", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_reminders_status_due", "task_reminders", ["status", "due_at"])
    op.create_index("ix_task_reminders_advance", "task_reminders", ["status", "advance_delivered", "advance_scheduled_at"])
    op.create_index("ix_task_reminders_due_poll", "task_reminders", ["status", "due_delivered", "due_at"])

    # 5. Table: user_notifications
    op.create_table(
        "user_notifications",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("reminder_id", sa.Uuid(), nullable=True),
        sa.Column("conversation_id", sa.Uuid(), nullable=True),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("is_read", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reminder_id"], ["task_reminders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_user_notifications_user_unread", "user_notifications", ["user_id", "is_read", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_user_notifications_user_unread", table_name="user_notifications")
    op.drop_table("user_notifications")

    op.drop_index("ix_task_reminders_due_poll", table_name="task_reminders")
    op.drop_index("ix_task_reminders_advance", table_name="task_reminders")
    op.drop_index("ix_task_reminders_status_due", table_name="task_reminders")
    op.drop_table("task_reminders")

    op.drop_index("ix_user_message_deletions_user_msg", table_name="user_message_deletions")
    op.drop_table("user_message_deletions")

    op.drop_index("ix_message_attachments_msg", table_name="message_attachments")
    op.drop_index("ix_message_attachments_conv", table_name="message_attachments")
    op.drop_table("message_attachments")

    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_constraint("fk_messages_deleted_by_id", type_="foreignkey")
        batch_op.drop_column("deleted_by_id")
        batch_op.drop_column("deleted_at")
        batch_op.drop_column("is_deleted_for_everyone")
