"""
Revision ID: 9594c79c1cd3
Revises:
Create Date: 2025-08-31 23:56:00.000000

"""

from collections.abc import Sequence

from alembic import op
from migrations.helpers import get_qualified_name

revision: str = "9594c79c1cd3"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    procurements_table = get_qualified_name("procurements")
    procurement_analyses_table = get_qualified_name("procurement_analyses")
    file_records_table = get_qualified_name("file_records")
    history_table = get_qualified_name("procurement_analysis_status_history")
    procurement_analysis_status_type = get_qualified_name("procurement_analysis_status")
    votes_table = get_qualified_name("votes")
    vote_type = get_qualified_name("vote_type")
    donations_table = get_qualified_name("donations")
    budget_ledgers_table = get_qualified_name("budget_ledgers")
    transaction_type = get_qualified_name("transaction_type")

    op.execute('CREATE EXTENSION IF NOT EXISTS "uuid-ossp";')

    op.execute(
        f"""
        CREATE TYPE {procurement_analysis_status_type} AS ENUM (
            'PENDING_ANALYSIS',
            'ANALYSIS_IN_PROGRESS',
            'ANALYSIS_SUCCESSFUL',
            'ANALYSIS_FAILED'
        );

        CREATE TYPE {vote_type} AS ENUM ('UP', 'DOWN');

        CREATE TYPE {transaction_type} AS ENUM ('DONATION', 'EXPENSE');

        CREATE TABLE {procurements_table} (
            procurement_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
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
            votes_count INTEGER NOT NULL DEFAULT 0,
            UNIQUE (pncp_control_number, version_number)
        );

        CREATE TABLE {procurement_analyses_table} (
            analysis_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            procurement_control_number VARCHAR(255) NOT NULL,
            version_number INTEGER NOT NULL,
            analysis_date TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            status {procurement_analysis_status_type} NOT NULL,
            retry_count SMALLINT NOT NULL DEFAULT 0,
            votes_count INTEGER NOT NULL DEFAULT 0,
            risk_score SMALLINT,
            risk_score_rationale TEXT,
            procurement_summary TEXT,
            analysis_summary TEXT,
            red_flags JSONB,
            seo_keywords TEXT[],
            warnings TEXT[],
            document_hash VARCHAR(64),
            original_documents_gcs_path VARCHAR,
            processed_documents_gcs_path VARCHAR,
            input_tokens_used INTEGER,
            output_tokens_used INTEGER,
            FOREIGN KEY (procurement_control_number, version_number)
                REFERENCES {procurements_table}(pncp_control_number, version_number)
        );

        CREATE TABLE {file_records_table} (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            analysis_id UUID NOT NULL REFERENCES {procurement_analyses_table}(analysis_id),
            file_name VARCHAR NOT NULL,
            gcs_path VARCHAR NOT NULL,
            extension VARCHAR,
            size_bytes INTEGER NOT NULL,
            nesting_level INTEGER NOT NULL,
            included_in_analysis BOOLEAN NOT NULL,
            exclusion_reason VARCHAR,
            prioritization_logic VARCHAR
        );

        CREATE TABLE {history_table} (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            analysis_id UUID NOT NULL REFERENCES {procurement_analyses_table}(analysis_id),
            status {procurement_analysis_status_type} NOT NULL,
            details TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE {votes_table} (
            vote_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            procurement_control_number VARCHAR NOT NULL,
            version_number INTEGER NOT NULL,
            user_id UUID NOT NULL,
            vote_type {vote_type} NOT NULL,
            FOREIGN KEY (procurement_control_number, version_number)
                REFERENCES {procurements_table}(pncp_control_number, version_number),
            UNIQUE (procurement_control_number, version_number, user_id)
        );

        -- Indexes for procurements table
        CREATE INDEX idx_procurements_pncp_control_number_version_number
            ON {procurements_table} (pncp_control_number, version_number DESC);
        CREATE INDEX idx_procurements_content_hash
            ON {procurements_table} (content_hash);
        CREATE INDEX idx_procurements_procurement_year
            ON {procurements_table} (procurement_year);
        CREATE INDEX idx_procurements_modality_id
            ON {procurements_table} (modality_id);
        CREATE INDEX idx_procurements_is_srp
            ON {procurements_table} (is_srp);
        CREATE INDEX idx_procurements_total_awarded_value
            ON {procurements_table} (total_awarded_value);
        CREATE INDEX idx_procurements_total_estimated_value
            ON {procurements_table} (total_estimated_value);
        CREATE INDEX idx_procurements_publication_date
            ON {procurements_table} (pncp_publication_date);


        -- Indexes for procurement_analyses table
        CREATE INDEX idx_procurement_analyses_status
            ON {procurement_analyses_table} (status);
        CREATE INDEX idx_procurement_analyses_document_hash
            ON {procurement_analyses_table} (document_hash);
        CREATE INDEX idx_procurement_analyses_risk_score
            ON {procurement_analyses_table} (risk_score);
        CREATE INDEX idx_procurement_analyses_analysis_date
            ON {procurement_analyses_table} (analysis_date);


        -- Indexes for file_records table
        CREATE INDEX idx_file_records_analysis_id
            ON {file_records_table} (analysis_id);
        CREATE INDEX idx_file_records_included_in_analysis
            ON {file_records_table} (included_in_analysis);


        -- Indexes for procurement_analysis_status_history table
        CREATE INDEX idx_procurement_analysis_status_history_analysis_id
            ON {history_table} (analysis_id);

        -- Indexes for votes table
        CREATE INDEX idx_votes_procurement
            ON {votes_table} (procurement_control_number, version_number);

        CREATE TABLE {donations_table} (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            donor_identifier VARCHAR NOT NULL,
            amount DECIMAL(10, 2) NOT NULL,
            transaction_id VARCHAR,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        CREATE TABLE {budget_ledgers_table} (
            id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            transaction_type {transaction_type} NOT NULL,
            amount DECIMAL(10, 2) NOT NULL,
            related_analysis_id UUID REFERENCES {procurement_analyses_table}(analysis_id),
            related_donation_id UUID REFERENCES {donations_table}(id),
            description TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );

        -- Indexes for donations table
        CREATE INDEX idx_donations_donor_identifier ON {donations_table} (donor_identifier);
        CREATE INDEX idx_donations_transaction_id ON {donations_table} (transaction_id);
        CREATE INDEX idx_donations_created_at ON {donations_table} (created_at);

        -- Indexes for budget_ledgers table
        CREATE INDEX idx_budget_ledgers_related_analysis_id ON {budget_ledgers_table} (related_analysis_id);
        CREATE INDEX idx_budget_ledgers_related_donation_id ON {budget_ledgers_table} (related_donation_id);
        CREATE INDEX idx_budget_ledgers_created_at ON {budget_ledgers_table} (created_at);
    """
    )


def downgrade() -> None:
    procurements_table = get_qualified_name("procurements")
    procurement_analyses_table = get_qualified_name("procurement_analyses")
    file_records_table = get_qualified_name("file_records")
    history_table = get_qualified_name("procurement_analysis_status_history")
    procurement_analysis_status_type = get_qualified_name("procurement_analysis_status")
    votes_table = get_qualified_name("votes")
    vote_type = get_qualified_name("vote_type")
    donations_table = get_qualified_name("donations")
    budget_ledgers_table = get_qualified_name("budget_ledgers")
    transaction_type = get_qualified_name("transaction_type")

    op.execute(
        f"""
        ALTER TABLE {procurement_analyses_table} RENAME COLUMN votes_count TO votes_count_dropped;
        ALTER TABLE {procurement_analyses_table} RENAME COLUMN retry_count TO retry_count_dropped;
        ALTER TABLE {procurements_table} RENAME TO {procurements_table}_dropped;
        ALTER TABLE {procurement_analyses_table} RENAME TO {procurement_analyses_table}_dropped;
        ALTER TABLE {file_records_table} RENAME TO {file_records_table}_dropped;
        ALTER TABLE {history_table} RENAME TO {history_table}_dropped;
        ALTER TABLE {votes_table} RENAME TO {votes_table}_dropped;
        ALTER TABLE {donations_table} RENAME TO {donations_table}_dropped;
        ALTER TABLE {budget_ledgers_table} RENAME TO {budget_ledgers_table}_dropped;
        ALTER TYPE {procurement_analysis_status_type} RENAME TO {procurement_analysis_status_type}_dropped;
        ALTER TYPE {vote_type} RENAME TO {vote_type}_dropped;
        ALTER TYPE {transaction_type} RENAME TO {transaction_type}_dropped;
        """
    )
