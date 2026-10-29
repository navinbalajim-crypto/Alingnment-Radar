"""Add per-user consent flags for external draft processing (default disabled).

Revision ID: 20261020_0006
Revises: 20261020_0005
Create Date: 2026-10-20 18:00:00

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "20261020_0006"
down_revision: Union[str, None] = "20261020_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

COLUMNS = ("ai_draft_analysis_consent", "ai_autocomplete_consent", "draft_recommendations_consent")


def upgrade() -> None:
    for name in COLUMNS:
        op.add_column("users", sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        for name in COLUMNS:
            batch.drop_column(name)
