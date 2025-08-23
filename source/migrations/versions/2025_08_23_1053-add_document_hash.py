"""add_document_hash

Revision ID: 3c4d5e6f7g8h
Revises: 2b3c4d5e6f7g
Create Date: 2025-08-23 10:53:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3c4d5e6f7g8h'
down_revision: Union[str, None] = '2b3c4d5e6f7g'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('procurement_analysis', sa.Column('document_hash', sa.String(length=64), nullable=True))
    op.create_index('ix_document_hash', 'procurement_analysis', ['document_hash'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_document_hash', 'procurement_analysis')
    op.drop_column('procurement_analysis', 'document_hash')
