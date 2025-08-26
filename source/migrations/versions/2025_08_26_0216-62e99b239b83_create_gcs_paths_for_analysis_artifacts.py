from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

revision: str = "62e99b239b83"
down_revision: str | None = "98d6cf46a2cc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table_name = get_table_name("procurement_analysis")
    op.execute(f"ALTER TABLE {table_name} ADD COLUMN original_documents_gcs_path VARCHAR;")
    op.execute(f"ALTER TABLE {table_name} ADD COLUMN processed_documents_gcs_path VARCHAR;")


def downgrade() -> None:
    table_name = get_table_name("procurement_analysis")
    op.execute(f"ALTER TABLE {table_name} DROP COLUMN processed_documents_gcs_path;")
    op.execute(f"ALTER TABLE {table_name} DROP COLUMN original_documents_gcs_path;")
