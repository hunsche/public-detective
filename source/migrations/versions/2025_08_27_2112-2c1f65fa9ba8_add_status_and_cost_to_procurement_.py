from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

revision: str = "2c1f65fa9ba8"
down_revision: str | None = "67757d277ba1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table_name = get_table_name("procurement_analysis")
    enum_name = "analysis_status"

    op.execute(
        f"""
        CREATE TYPE {enum_name} AS ENUM (
            'PENDING_ANALYSIS',
            'ANALYSIS_IN_PROGRESS',
            'ANALYSIS_SUCCESSFUL',
            'ANALYSIS_FAILED'
        );
        """
    )

    op.execute(
        f"""
        ALTER TABLE {table_name}
        ADD COLUMN status {enum_name},
        ADD COLUMN estimated_cost DECIMAL(10, 4);
        """
    )


def downgrade() -> None:
    table_name = get_table_name("procurement_analysis")
    enum_name = "analysis_status"

    op.execute(
        f"""
        ALTER TABLE {table_name}
        DROP COLUMN status,
        DROP COLUMN estimated_cost;
        """
    )

    op.execute(f"DROP TYPE {enum_name};")
