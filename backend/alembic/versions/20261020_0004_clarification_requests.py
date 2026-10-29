"""Track receiver-initiated clarification requests on alignment findings.

Revision ID: 20261020_0004
Revises: 20261019_0003
Create Date: 2026-10-20 10:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261020_0004"
down_revision: Union[str, None] = "20261019_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("alignment_findings", schema=None) as batch_op:
        batch_op.add_column(sa.Column("clarification_request_message_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("clarification_requested_by_id", sa.Uuid(), nullable=True))
        batch_op.add_column(sa.Column("clarification_requested_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("alignment_findings", schema=None) as batch_op:
        batch_op.drop_column("clarification_requested_at")
        batch_op.drop_column("clarification_requested_by_id")
        batch_op.drop_column("clarification_request_message_id")
