"""Add alignment lifecycle states and recommendation dismissal columns.

Revision ID: 20261019_0003
Revises: 20261019_0002
Create Date: 2026-10-19 20:05:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261019_0003"
down_revision: Union[str, None] = "20261019_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Update alignment_findings table
    with op.batch_alter_table("alignment_findings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("title", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("severity", sa.String(length=20), server_default="medium", nullable=False))
        batch_op.add_column(sa.Column("status", sa.String(length=50), server_default="detected", nullable=False))
        batch_op.add_column(sa.Column("suggested_reply", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("intended_outcome", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("status_history", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("confirmations", sa.JSON(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("resolution_evidence", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("resolved_by_id", sa.Uuid(), nullable=True))
        batch_op.create_index("ix_alignment_findings_status", ["status"])
        batch_op.create_index("ix_alignment_findings_conv_status", ["conversation_id", "status"])

    # 2. Update recommendation_items table
    with op.batch_alter_table("recommendation_items", schema=None) as batch_op:
        batch_op.add_column(sa.Column("is_dismissed", sa.Boolean(), server_default=sa.false(), nullable=False))
        batch_op.add_column(sa.Column("dismissed_by_id", sa.Uuid(), nullable=True))
        batch_op.create_index("ix_recommendation_items_is_dismissed", ["is_dismissed"])
        batch_op.create_index("ix_recommendation_conv_dismissed", ["conversation_id", "is_dismissed"])


def downgrade() -> None:
    with op.batch_alter_table("recommendation_items", schema=None) as batch_op:
        batch_op.drop_index("ix_recommendation_conv_dismissed")
        batch_op.drop_index("ix_recommendation_items_is_dismissed")
        batch_op.drop_column("dismissed_by_id")
        batch_op.drop_column("is_dismissed")

    with op.batch_alter_table("alignment_findings", schema=None) as batch_op:
        batch_op.drop_index("ix_alignment_findings_conv_status")
        batch_op.drop_index("ix_alignment_findings_status")
        batch_op.drop_column("resolved_by_id")
        batch_op.drop_column("resolved_at")
        batch_op.drop_column("resolution_evidence")
        batch_op.drop_column("confirmations")
        batch_op.drop_column("status_history")
        batch_op.drop_column("intended_outcome")
        batch_op.drop_column("suggested_reply")
        batch_op.drop_column("status")
        batch_op.drop_column("severity")
        batch_op.drop_column("title")
