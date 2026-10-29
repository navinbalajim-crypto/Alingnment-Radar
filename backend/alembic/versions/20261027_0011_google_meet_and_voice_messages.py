"""Add Google Meet meeting invitations and voice note transcripts tables.

Revision ID: 20261027_0011
Revises: 20261027_0010
Create Date: 2026-10-27 18:15:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261027_0011"
down_revision: Union[str, None] = "20261027_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create meeting_invitations table
    op.create_table(
        "meeting_invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("creator_id", sa.Uuid(), nullable=True),
        sa.Column("message_id", sa.Uuid(), nullable=True),
        sa.Column("provider", sa.String(length=50), server_default="google_meet", nullable=False),
        sa.Column("meeting_uri", sa.String(length=1024), nullable=False),
        sa.Column("meeting_code", sa.String(length=100), nullable=True),
        sa.Column("space_name", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), server_default="active", nullable=False),
        sa.Column("client_token", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["conversation_id"], ["conversations.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["creator_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_meeting_invitations_conv_created",
        "meeting_invitations",
        ["conversation_id", "created_at"],
    )
    op.create_index(
        "ix_meeting_invitations_client_token",
        "meeting_invitations",
        ["conversation_id", "client_token"],
    )

    # 2. Create voice_transcripts table
    op.create_table(
        "voice_transcripts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("attachment_id", sa.Uuid(), nullable=True),
        sa.Column("duration_seconds", sa.Float(), nullable=True),
        sa.Column("source_language", sa.String(length=20), nullable=True),
        sa.Column("transcript_text", sa.Text(), nullable=True),
        sa.Column("transcript_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("transcription_status", sa.String(length=50), server_default="uploaded", nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("translations", sa.JSON(), nullable=False),
        sa.Column("provider_metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attachment_id"], ["message_attachments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id", name="uq_voice_transcripts_message_id"),
    )
    op.create_index(
        "ix_voice_transcripts_status",
        "voice_transcripts",
        ["transcription_status"],
    )


def downgrade() -> None:
    op.drop_index("ix_voice_transcripts_status", table_name="voice_transcripts")
    op.drop_table("voice_transcripts")

    op.drop_index("ix_meeting_invitations_client_token", table_name="meeting_invitations")
    op.drop_index("ix_meeting_invitations_conv_created", table_name="meeting_invitations")
    op.drop_table("meeting_invitations")
