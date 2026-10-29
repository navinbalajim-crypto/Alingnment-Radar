"""Add avatar_url to conversations (group display pictures).

Revision ID: 20261029_0012
Revises: 20261027_0011
Create Date: 2026-10-29 00:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261029_0012"
down_revision: Union[str, None] = "20261027_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("conversations", sa.Column("avatar_url", sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column("conversations", "avatar_url")
