from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_table_name

# revision identifiers, used by Alembic.
revision: str = "014b9fad2247"
down_revision: str | None = "fase1ts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Pluralizes all table names."""
    op.execute(f"ALTER TABLE {get_table_name('procurement_analysis')} RENAME TO procurement_analyses;")
    op.execute(f"ALTER TABLE {get_table_name('file_record')} RENAME TO file_records;")
    op.execute(f"ALTER TABLE {get_table_name('procurement')} RENAME TO procurements;")


def downgrade() -> None:
    """Singularizes all table names."""
    op.execute("ALTER TABLE procurement_analyses RENAME TO procurement_analysis;")
    op.execute("ALTER TABLE file_records RENAME TO file_record;")
    op.execute("ALTER TABLE procurements RENAME TO procurement;")
