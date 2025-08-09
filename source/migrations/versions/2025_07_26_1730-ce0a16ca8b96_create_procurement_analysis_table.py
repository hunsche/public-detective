from typing import Sequence, Union

from alembic import op


revision: str = "ce0a16ca8b96"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE procurement_analysis (
            id SERIAL PRIMARY KEY,
            procurement_control_number TEXT UNIQUE NOT NULL,
            risk_score INT,
            summary TEXT,
            red_flags JSONB,
            warnings TEXT[],
            gcs_document_url TEXT,
            analysis_date TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX idx_procurement_analysis_control_number ON procurement_analysis (procurement_control_number);
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DROP TABLE IF EXISTS procurement_analysis;
        """
    )
