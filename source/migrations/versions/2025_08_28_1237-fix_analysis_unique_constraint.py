"""
Fix unique constraint on procurement_analysis.

Revision ID: fase1fix
Revises: fase1hash
Create Date: 2025-08-28 12:37:00.000000

"""

from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

# revision identifiers, used by Alembic.
revision: str = "fase1fix"
down_revision: str | None = "fase1hash"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    analysis_table = get_table_name("procurement_analysis")
    base_analysis_table = "procurement_analysis"
    op.execute(
        f"ALTER TABLE {analysis_table} DROP CONSTRAINT IF EXISTS {base_analysis_table}_procurement_control_number_key;"
    )  # nosec B608
    op.execute(
        f"CREATE UNIQUE INDEX idx_procurement_analysis_pid_ver ON {analysis_table} "
        "(procurement_control_number, version_number);"
    )  # nosec B608


def downgrade() -> None:
    analysis_table = get_table_name("procurement_analysis")
    op.execute("DROP INDEX idx_procurement_analysis_pid_ver;")
    op.execute(f"ALTER TABLE {analysis_table} ADD UNIQUE (procurement_control_number);")
