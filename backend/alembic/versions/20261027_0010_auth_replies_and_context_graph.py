"""Add password authentication, reply-to message references, and conversation context graph.

Revision ID: 20261027_0010
Revises: 20261027_0009
Create Date: 2026-10-27 16:20:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261027_0010"
down_revision: Union[str, None] = "20261027_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Add password_hash to users table
    with op.batch_alter_table("users") as batch_op:
        batch_op.add_column(sa.Column("password_hash", sa.String(length=255), nullable=True))

    # 2. Add reply_to_message_id to messages table
    with op.batch_alter_table("messages") as batch_op:
        batch_op.add_column(sa.Column("reply_to_message_id", sa.Uuid(), nullable=True))
        batch_op.create_foreign_key(
            "fk_messages_reply_to_message_id",
            "messages",
            ["reply_to_message_id"],
            ["id"],
            ondelete="SET NULL",
        )
        batch_op.create_index("ix_messages_reply_to_msg", ["reply_to_message_id"])

    # 3. Create context_nodes table
    op.create_table(
        "context_nodes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("node_type", sa.String(length=50), server_default="task", nullable=False),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("responsible_person", sa.String(length=100), nullable=True),
        sa.Column("responsible_user_id", sa.Uuid(), nullable=True),
        sa.Column("deadline", sa.String(length=100), nullable=True),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="pending", nullable=False),
        sa.Column("evidence_message_ids", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.8", nullable=False),
        sa.Column("is_resolved", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("last_updated_by_message_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["responsible_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["last_updated_by_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_context_nodes_conv_status", "context_nodes", ["conversation_id", "status"])
    op.create_index("ix_context_nodes_conv_type", "context_nodes", ["conversation_id", "node_type"])

    # 4. Create context_inconsistencies table
    op.create_table(
        "context_inconsistencies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("node_id", sa.Uuid(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("earlier_evidence_message_id", sa.Uuid(), nullable=True),
        sa.Column("later_evidence_message_id", sa.Uuid(), nullable=True),
        sa.Column("clarification_prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=50), server_default="detected", nullable=False),
        sa.Column("is_dismissed", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["node_id"], ["context_nodes.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["earlier_evidence_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["later_evidence_message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_context_inconsistencies_conv_status",
        "context_inconsistencies",
        ["conversation_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_context_inconsistencies_conv_status", table_name="context_inconsistencies")
    op.drop_table("context_inconsistencies")

    op.drop_index("ix_context_nodes_conv_type", table_name="context_nodes")
    op.drop_index("ix_context_nodes_conv_status", table_name="context_nodes")
    op.drop_table("context_nodes")

    with op.batch_alter_table("messages") as batch_op:
        batch_op.drop_index("ix_messages_reply_to_msg")
        batch_op.drop_constraint("fk_messages_reply_to_message_id", type_="foreignkey")
        batch_op.drop_column("reply_to_message_id")

    with op.batch_alter_table("users") as batch_op:
        batch_op.drop_column("password_hash")
