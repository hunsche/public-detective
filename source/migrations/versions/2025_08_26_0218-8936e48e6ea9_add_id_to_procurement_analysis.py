from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

revision: str = "8936e48e6ea9"
down_revision: str | None = "62e99b239b83"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table_name = get_table_name("procurement_analysis")
    op.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT IF EXISTS procurement_analysis_pkey CASCADE;")
    op.execute(f"ALTER TABLE {table_name} ADD COLUMN id SERIAL PRIMARY KEY;")
    op.execute(f"ALTER TABLE {table_name} ADD UNIQUE (procurement_control_number);")


def downgrade() -> None:
    table_name = get_table_name("procurement_analysis")
    op.execute(f"ALTER TABLE {table_name} DROP CONSTRAINT procurement_analysis_procurement_control_number_key;")
    op.execute(f"ALTER TABLE {table_name} DROP COLUMN id;")
    op.execute(f"ALTER TABLE {table_name} ADD PRIMARY KEY (procurement_control_number);")
