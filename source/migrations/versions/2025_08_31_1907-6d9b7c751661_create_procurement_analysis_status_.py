from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from source.migrations.helpers import get_qualified_name


revision: str = '6d9b7c751661'
down_revision: Union[str, None] = 'b7179b0a29e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    history_table = get_qualified_name("procurement_analysis_status_history")
    analyses_table = get_qualified_name("procurement_analyses")
    op.execute(
        f"""
        CREATE TABLE {history_table} (
            id SERIAL PRIMARY KEY,
            analysis_id INTEGER NOT NULL,
            status VARCHAR(255) NOT NULL,
            details TEXT,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            CONSTRAINT fk_analysis
                FOREIGN KEY(analysis_id)
                REFERENCES {analyses_table}(analysis_id)
                ON DELETE CASCADE
        );
        """
    )
    op.execute(
        f"""
        CREATE INDEX idx_procurement_analysis_status_history_analysis_id
        ON {history_table}(analysis_id);
        """
    )


def downgrade() -> None:
    history_table = get_qualified_name("procurement_analysis_status_history")
    op.execute(f"ALTER TABLE {history_table} RENAME TO {history_table}_dropped;")
