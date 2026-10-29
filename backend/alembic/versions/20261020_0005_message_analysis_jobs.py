"""Add durable per-message analysis job table.

Revision ID: 20261020_0005
Revises: 20261020_0004
Create Date: 2026-10-20 14:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261020_0005"
down_revision: Union[str, None] = "20261020_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "message_analysis_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("message_id", sa.Uuid(), sa.ForeignKey("messages.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("conversation_id", sa.Uuid(), sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("outcome", sa.String(length=50), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_message_analysis_jobs_conversation_id", "message_analysis_jobs", ["conversation_id"])
    op.create_index("ix_analysis_jobs_status_next", "message_analysis_jobs", ["status", "next_attempt_at"])


def downgrade() -> None:
    op.drop_index("ix_analysis_jobs_status_next", table_name="message_analysis_jobs")
    op.drop_index("ix_message_analysis_jobs_conversation_id", table_name="message_analysis_jobs")
    op.drop_table("message_analysis_jobs")
