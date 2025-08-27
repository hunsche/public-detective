from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

revision: str = "67757d277ba1"
down_revision: str | None = "9595c4dc19b4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table_name = get_table_name("procurement")
    op.execute(f"ALTER TABLE {table_name} ADD COLUMN raw_data JSONB;")


def downgrade() -> None:
    table_name = get_table_name("procurement")
    op.execute(f"ALTER TABLE {table_name} DROP COLUMN raw_data;")
