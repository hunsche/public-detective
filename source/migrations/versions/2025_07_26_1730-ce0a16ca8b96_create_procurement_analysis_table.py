"""
Creates the initial procurement_analysis table.

Revision ID: ce0a16ca8b96
Revises:
Create Date: 2025-07-26 17:30:11.111111

"""

import os
from collections.abc import Sequence

from alembic import op

revision: str = "ce0a16ca8b96"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """
    Creates the procurement_analysis table with all necessary columns
    and indexes using raw SQL commands for full control.
    """
    schema_name = os.getenv("POSTGRES_DB_SCHEMA")
    table_name = "procurement_analysis"
    if schema_name:
        table_name = f"{schema_name}.{table_name}"

    op.execute(f"DROP TABLE IF EXISTS {table_name}_dropped CASCADE;")
    op.execute(
        f"""
        CREATE TABLE {table_name} (
            procurement_control_number VARCHAR(255) NOT NULL,
            analysis_date TIMESTAMP WITHOUT TIME ZONE DEFAULT now() NOT NULL,
            risk_score SMALLINT,
            risk_score_rationale TEXT,
            summary TEXT,
            red_flags JSONB,
            warnings TEXT[],
            document_hash VARCHAR(64),
            original_documents_url VARCHAR(1024),
            processed_documents_url VARCHAR(1024),
            PRIMARY KEY (procurement_control_number)
        );
    """
    )
    op.execute(
        f"""
        CREATE INDEX ix_document_hash
        ON {table_name} (document_hash);
    """
    )


def downgrade() -> None:
    """
    Renames the table to a dropped state instead of permanently deleting it.
    This provides a safety net for rollbacks.
    """
    schema_name = os.getenv("POSTGRES_DB_SCHEMA")
    table_name = "procurement_analysis"
    if schema_name:
        table_name = f"{schema_name}.{table_name}"
        op.execute(f"DROP INDEX IF EXISTS {schema_name}.ix_document_hash;")
    else:
        op.execute("DROP INDEX IF EXISTS ix_document_hash;")

    op.execute(f"ALTER TABLE {table_name} RENAME TO procurement_analysis_dropped;")
