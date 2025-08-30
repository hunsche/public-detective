"""
Adds versioning to procurements, pre-analysis support and an overall status view.

Revision ID: fase1vers
Revises: 9595c4dc19b4
Create Date: 2025-08-28 12:34:56.789123

"""

from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

# revision identifiers, used by Alembic.
revision: str = "fase1vers"
down_revision: str | None = "9595c4dc19b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    procurement_table = get_table_name("procurement")
    analysis_table = get_table_name("procurement_analysis")
    procurement_base_name = "procurement"

    # ### Procurement Table Modifications ###
    op.execute(f"ALTER TABLE {procurement_table} DROP CONSTRAINT IF EXISTS {procurement_base_name}_pkey;")
    op.execute(
        f"ALTER TABLE {procurement_table} DROP CONSTRAINT IF EXISTS {procurement_base_name}_pncp_control_number_key;"
    )

    op.execute(f"ALTER TABLE {procurement_table} RENAME COLUMN id TO procurement_id;")
    op.execute(f"ALTER TABLE {procurement_table} ADD COLUMN version_number INTEGER;")
    op.execute(f"UPDATE {procurement_table} SET version_number = 1;")  # nosec B608
    op.execute(f"ALTER TABLE {procurement_table} ALTER COLUMN version_number SET NOT NULL;")
    op.execute(f"ALTER TABLE {procurement_table} ADD COLUMN raw_data JSONB;")
    op.execute(f"UPDATE {procurement_table} SET raw_data = '{{}}'::jsonb;")  # nosec B608
    op.execute(f"ALTER TABLE {procurement_table} ALTER COLUMN raw_data SET NOT NULL;")

    op.execute(f"ALTER TABLE {procurement_table} ADD PRIMARY KEY (pncp_control_number, version_number);")
    op.execute(
        f"""
        CREATE INDEX idx_procurement_pid_ver
        ON {procurement_table} (pncp_control_number, version_number DESC);
        """
    )

    # ### Procurement Analysis Table Modifications ###
    op.execute(f"ALTER TABLE {analysis_table} RENAME COLUMN id TO analysis_id;")
    op.execute(f"ALTER TABLE {analysis_table} ADD COLUMN version_number INTEGER;")
    op.execute(f"UPDATE {analysis_table} SET version_number = 1;")  # nosec B608
    op.execute(f"ALTER TABLE {analysis_table} ALTER COLUMN version_number SET NOT NULL;")

    op.execute(f"ALTER TABLE {analysis_table} ADD COLUMN estimated_cost DECIMAL(12, 6);")
    op.execute(f"ALTER TABLE {analysis_table} ADD COLUMN status VARCHAR(50);")
    op.execute(f"UPDATE {analysis_table} SET status = 'ANALYSIS_SUCCESSFUL';")  # nosec B608
    op.execute(f"ALTER TABLE {analysis_table} ALTER COLUMN status SET NOT NULL;")
    op.execute(
        f"ALTER TABLE {analysis_table} ADD CONSTRAINT chk_status "
        "CHECK (status IN ('PENDING_ANALYSIS', 'ANALYSIS_IN_PROGRESS', 'ANALYSIS_SUCCESSFUL', 'ANALYSIS_FAILED'));"
    )

    op.execute(
        f"""
        ALTER TABLE {analysis_table}
        ADD CONSTRAINT fk_procurement_version
        FOREIGN KEY (procurement_control_number, version_number)
        REFERENCES {procurement_table} (pncp_control_number, version_number);
        """
    )

    op.execute(
        f"""
        CREATE INDEX idx_analysis_pid_ver
        ON {analysis_table} (procurement_control_number, version_number);
        """
    )
    op.execute(f"CREATE INDEX idx_analysis_status ON {analysis_table} (status);")


def downgrade() -> None:
    procurement_table = get_table_name("procurement")
    analysis_table = get_table_name("procurement_analysis")

    op.execute(f"DROP INDEX {get_table_name('idx_analysis_status')};")
    op.execute(f"DROP INDEX {get_table_name('idx_analysis_pid_ver')};")
    op.execute(f"ALTER TABLE {analysis_table} DROP CONSTRAINT fk_procurement_version;")
    op.execute(f"ALTER TABLE {analysis_table} DROP CONSTRAINT chk_status;")

    op.execute(f"ALTER TABLE {analysis_table} RENAME COLUMN status TO status_dropped;")
    op.execute(f"ALTER TABLE {analysis_table} RENAME COLUMN estimated_cost TO estimated_cost_dropped;")
    op.execute(f"ALTER TABLE {analysis_table} RENAME COLUMN version_number TO version_number_dropped;")
    op.execute(f"ALTER TABLE {analysis_table} RENAME COLUMN analysis_id TO id;")

    op.execute(f"DROP INDEX {get_table_name('idx_procurement_pid_ver')};")
    procurement_base_name = "procurement"
    op.execute(f"ALTER TABLE {procurement_table} DROP CONSTRAINT {procurement_base_name}_pkey;")
    op.execute(f"ALTER TABLE {procurement_table} RENAME COLUMN raw_data TO raw_data_dropped;")
    op.execute(f"ALTER TABLE {procurement_table} RENAME COLUMN version_number TO version_number_dropped;")
    op.execute(f"ALTER TABLE {procurement_table} RENAME COLUMN procurement_id TO id;")
    op.execute(f"ALTER TABLE {procurement_table} ADD PRIMARY KEY (id);")
    op.execute(f"ALTER TABLE {procurement_table} ADD UNIQUE (pncp_control_number);")
