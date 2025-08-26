from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

revision: str = "0ce1492408b3"
down_revision: str | None = "8936e48e6ea9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table_name = get_table_name("file_record")
    ref_table_name = get_table_name("procurement_analysis")
    op.execute(
        f"""
        CREATE TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            analysis_id INTEGER NOT NULL REFERENCES {ref_table_name}(id),
            file_name VARCHAR NOT NULL,
            gcs_path VARCHAR NOT NULL,
            extension VARCHAR,
            size_bytes INTEGER NOT NULL,
            nesting_level INTEGER NOT NULL,
            included_in_analysis BOOLEAN NOT NULL,
            exclusion_reason VARCHAR,
            prioritization_logic VARCHAR
        );
    """
    )


def downgrade() -> None:
    table_name = get_table_name("file_record")
    op.execute(f"DROP TABLE {table_name};")
