"""
Revision ID: b7179b0a29e7
Revises:
Create Date: 2025-08-31 14:34:00.000000

"""
import os
from typing import Sequence, Union

from alembic import op


revision: str = 'b7179b0a29e7'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    schema_name = os.getenv("POSTGRES_DB_SCHEMA")

    def get_qualified_name(name):
        return f"{schema_name}.{name}" if schema_name else name

    procurements_table = get_qualified_name("procurements")
    procurement_analyses_table = get_qualified_name("procurement_analyses")
    file_records_table = get_qualified_name("file_records")
    procurement_analysis_status_type = get_qualified_name("procurement_analysis_status")

    op.execute(f"DROP TABLE IF EXISTS {file_records_table} CASCADE;")
    op.execute(f"DROP TABLE IF EXISTS {procurement_analyses_table} CASCADE;")
    op.execute(f"DROP TABLE IF EXISTS {procurements_table} CASCADE;")
    op.execute(f"DROP TYPE IF EXISTS {procurement_analysis_status_type} CASCADE;")

    op.execute(f'''
        CREATE TYPE {procurement_analysis_status_type} AS ENUM (
            'PENDING_ANALYSIS',
            'ANALYSIS_IN_PROGRESS',
            'ANALYSIS_SUCCESSFUL',
            'ANALYSIS_FAILED'
        );

        CREATE TABLE {procurements_table} (
            procurement_id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            pncp_control_number VARCHAR NOT NULL,
            proposal_opening_date TIMESTAMPTZ,
            proposal_closing_date TIMESTAMPTZ,
            object_description TEXT NOT NULL,
            total_awarded_value DOUBLE PRECISION,
            is_srp BOOLEAN NOT NULL,
            procurement_year INTEGER NOT NULL,
            procurement_sequence INTEGER NOT NULL,
            pncp_publication_date TIMESTAMPTZ NOT NULL,
            last_update_date TIMESTAMPTZ NOT NULL,
            modality_id INTEGER NOT NULL,
            procurement_status_id INTEGER NOT NULL,
            total_estimated_value DOUBLE PRECISION,
            version_number INTEGER NOT NULL,
            raw_data JSONB NOT NULL,
            content_hash VARCHAR(64),
            UNIQUE (pncp_control_number, version_number)
        );

        CREATE TABLE {procurement_analyses_table} (
            analysis_id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            procurement_control_number VARCHAR(255) NOT NULL,
            version_number INTEGER NOT NULL,
            analysis_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            status {procurement_analysis_status_type} NOT NULL,
            risk_score SMALLINT,
            risk_score_rationale TEXT,
            summary TEXT,
            red_flags JSONB,
            warnings TEXT[],
            document_hash VARCHAR(64),
            original_documents_url VARCHAR(1024),
            processed_documents_url VARCHAR(1024),
            original_documents_gcs_path VARCHAR,
            processed_documents_gcs_path VARCHAR,
            estimated_cost NUMERIC(12, 6),
            FOREIGN KEY (procurement_control_number, version_number) REFERENCES {procurements_table}(pncp_control_number, version_number),
            UNIQUE (procurement_control_number, version_number)
        );

        CREATE TABLE {file_records_table} (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            analysis_id INTEGER NOT NULL REFERENCES {procurement_analyses_table}(analysis_id),
            file_name VARCHAR NOT NULL,
            gcs_path VARCHAR NOT NULL,
            extension VARCHAR,
            size_bytes INTEGER NOT NULL,
            nesting_level INTEGER NOT NULL,
            included_in_analysis BOOLEAN NOT NULL,
            exclusion_reason VARCHAR,
            prioritization_logic VARCHAR
        );

        CREATE INDEX idx_analysis_status ON {procurement_analyses_table} USING btree (status);
        CREATE INDEX idx_procurement_pid_ver ON {procurements_table} USING btree (pncp_control_number, version_number DESC);
        CREATE INDEX ix_document_hash ON {procurement_analyses_table} USING btree (document_hash);
        CREATE INDEX ix_procurement_content_hash ON {procurements_table} USING btree (content_hash);
    ''')


def downgrade() -> None:
    schema_name = os.getenv("POSTGRES_DB_SCHEMA")

    def get_qualified_name(name):
        return f"{schema_name}.{name}" if schema_name else name

    procurements_table = get_qualified_name("procurements")
    procurement_analyses_table = get_qualified_name("procurement_analyses")
    file_records_table = get_qualified_name("file_records")
    procurement_analysis_status_type = get_qualified_name("procurement_analysis_status")

    op.execute(f"DROP TABLE IF EXISTS {file_records_table} CASCADE;")
    op.execute(f"DROP TABLE IF EXISTS {procurement_analyses_table} CASCADE;")
    op.execute(f"DROP TABLE IF EXISTS {procurements_table} CASCADE;")
    op.execute(f"DROP TYPE IF EXISTS {procurement_analysis_status_type} CASCADE;")
