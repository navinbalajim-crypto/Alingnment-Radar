"""Enforce client-message idempotency per sender with a partial unique index.

Revision ID: 20261020_0007
Revises: 20261020_0006
Create Date: 2026-10-20 19:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261020_0007"
down_revision: Union[str, None] = "20261020_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Fails loudly (rather than deleting data) if duplicate client ids already exist.
    op.create_index(
        "uq_messages_sender_client", "messages", ["conversation_id", "sender_id", "client_id"],
        unique=True,
        sqlite_where=sa.text("client_id IS NOT NULL"),
        postgresql_where=sa.text("client_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_messages_sender_client", table_name="messages")
