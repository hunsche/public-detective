from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

revision: str = "9595c4dc19b4"
down_revision: str | None = "0ce1492408b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table_name = get_table_name("procurement")
    op.execute(
        f"""
        CREATE TABLE {table_name} (
            id SERIAL PRIMARY KEY,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            pncp_control_number VARCHAR UNIQUE NOT NULL,
            proposal_opening_date TIMESTAMPTZ,
            proposal_closing_date TIMESTAMPTZ,
            object_description TEXT NOT NULL,
            total_awarded_value FLOAT,
            is_srp BOOLEAN NOT NULL,
            procurement_year INTEGER NOT NULL,
            procurement_sequence INTEGER NOT NULL,
            pncp_publication_date TIMESTAMPTZ NOT NULL,
            last_update_date TIMESTAMPTZ NOT NULL,
            modality_id INTEGER NOT NULL,
            procurement_status_id INTEGER NOT NULL,
            total_estimated_value FLOAT
        );
    """
    )


def downgrade() -> None:
    table_name = get_table_name("procurement")
    op.execute(f"DROP TABLE {table_name};")
