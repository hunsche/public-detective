"""
Add created_at and updated_at to procurement_analysis.

Revision ID: fase1ts
Revises: fase1fix
Create Date: 2025-08-28 12:38:00.000000

"""

from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

# revision identifiers, used by Alembic.
revision: str = "fase1ts"
down_revision: str | None = "fase1fix"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    table_name = get_table_name("procurement_analysis")
    op.execute(f"ALTER TABLE {table_name} ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now();")
    op.execute(f"ALTER TABLE {table_name} ADD COLUMN updated_at TIMESTAMPTZ NOT NULL DEFAULT now();")


def downgrade() -> None:
    table_name = get_table_name("procurement_analysis")
    op.execute(f"ALTER TABLE {table_name} DROP COLUMN updated_at;")
    op.execute(f"ALTER TABLE {table_name} DROP COLUMN created_at;")
