from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '98d6cf46a2cc'
down_revision: Union[str, None] = 'ce0a16ca8b96'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """
    Changes the analysis_date column from TIMESTAMP to TIMESTAMPZ.
    The USING clause is necessary to cast the existing data correctly, assuming
    the naive timestamps were stored in UTC.
    """
    op.execute(
        """
        ALTER TABLE procurement_analysis
        ALTER COLUMN analysis_date TYPE TIMESTAMP WITH TIME ZONE
        USING (analysis_date AT TIME ZONE 'UTC');
    """
    )


def downgrade() -> None:
    """
    Reverts the analysis_date column from TIMESTAMPZ back to TIMESTAMP.
    """
    op.execute(
        """
        ALTER TABLE procurement_analysis
        ALTER COLUMN analysis_date TYPE TIMESTAMP WITHOUT TIME ZONE;
    """
    )
