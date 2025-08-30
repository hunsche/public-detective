"""
Add content_hash to procurement table.

Revision ID: fase1hash
Revises: fase1view
Create Date: 2025-08-28 12:36:00.000000

"""

from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

# revision identifiers, used by Alembic.
revision: str = "fase1hash"
down_revision: str | None = "fase1view"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table_name = get_table_name("procurement")
    op.execute(f"ALTER TABLE {table_name} ADD COLUMN content_hash VARCHAR(64);")  # nosec B608
    op.execute(f"CREATE INDEX ix_procurement_content_hash ON {table_name} (content_hash);")  # nosec B608


def downgrade() -> None:
    table_name = get_table_name("procurement")
    op.execute("DROP INDEX ix_procurement_content_hash;")
    op.execute(f"ALTER TABLE {table_name} DROP COLUMN content_hash;")
