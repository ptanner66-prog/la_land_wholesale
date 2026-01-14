"""add_result_column_to_outreach_attempt

Revision ID: 866453a7d469
Revises: 0000_sqlite_init
Create Date: 2025-12-05 02:36:17.959236

"""
from __future__ import annotations

from typing import Sequence

from alembic import op
import sqlalchemy as sa
import geoalchemy2


# revision identifiers, used by Alembic.
revision: str = '866453a7d469'
down_revision: str | None = '0000_sqlite_init'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Add result column to outreach_attempt table."""
    op.add_column('outreach_attempt', sa.Column('result', sa.String(50), nullable=True))


def downgrade() -> None:
    """Remove result column from outreach_attempt table."""
    op.drop_column('outreach_attempt', 'result')
