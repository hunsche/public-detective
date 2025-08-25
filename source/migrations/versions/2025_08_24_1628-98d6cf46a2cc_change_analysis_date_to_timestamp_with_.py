"""change analysis_date to timestamp with timezone

Revision ID: 98d6cf46a2cc
Revises: ce0a16ca8b96
Create Date: 2025-08-24 16:28:38.204523

"""

import os

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "98d6cf46a2cc"
down_revision: str | None = "ce0a16ca8b96"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    """
    Changes the analysis_date column from DATE to TIMESTAMP WITH TIME ZONE.
    The USING clause is necessary to cast the existing data correctly, assuming
    the naive dates were stored in UTC.
    """
    schema_name = os.getenv("POSTGRES_DB_SCHEMA")
    table_name = "procurement_analysis"
    if schema_name:
        table_name = f"{schema_name}.{table_name}"

    op.execute(
        f"""
        ALTER TABLE {table_name}
        ALTER COLUMN analysis_date TYPE TIMESTAMP WITH TIME ZONE
        USING (analysis_date AT TIME ZONE 'UTC');
    """
    )


def downgrade() -> None:
    """
    Reverts the analysis_date column from TIMESTAMP WITH TIME ZONE back to DATE.
    This is a destructive operation as it will truncate the time part of the timestamp.
    """
    schema_name = os.getenv("POSTGRES_DB_SCHEMA")
    table_name = "procurement_analysis"
    if schema_name:
        table_name = f"{schema_name}.{table_name}"

    op.execute(
        f"""
        ALTER TABLE {table_name}
        ALTER COLUMN analysis_date TYPE DATE;
    """
    )
