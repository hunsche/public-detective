"""add_new_analysis_columns

Revision ID: 4d5e6f7g8h9i
Revises: ce0a16ca8b96
Create Date: 2025-08-23 11:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4d5e6f7g8h9i'
down_revision: Union[str, None] = 'ce0a16ca8b96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('procurement_analysis', sa.Column('risk_score_rationale', sa.Text(), nullable=True))
    op.add_column('procurement_analysis', sa.Column('document_hash', sa.String(length=64), nullable=True))
    op.add_column('procurement_analysis', sa.Column('original_documents_url', sa.String(), nullable=True))
    op.add_column('procurement_analysis', sa.Column('processed_documents_url', sa.String(), nullable=True))
    op.create_index('ix_document_hash', 'procurement_analysis', ['document_hash'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_document_hash', 'procurement_analysis')
    op.drop_column('procurement_analysis', 'processed_documents_url')
    op.drop_column('procurement_analysis', 'original_documents_url')
    op.drop_column('procurement_analysis', 'document_hash')
    op.drop_column('procurement_analysis', 'risk_score_rationale')
