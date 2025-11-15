"""add_geographic_scope_to_procurements

Revision ID: 79c8e9e6e83c
Revises: 9594c79c1cd3
Create Date: 2025-11-15 15:49:50.513576

"""

from alembic import op

# revision identifiers, used by Alembic.
revision = "79c8e9e6e83c"
down_revision = "9594c79c1cd3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Adds the geographic_scope column to the procurements table."""
    op.execute(
        """
        ALTER TABLE procurements
        ADD COLUMN geographic_scope VARCHAR(255);
        """
    )


def downgrade() -> None:
    """Removes the geographic_scope column from the procurements table."""
    op.execute(
        """
        ALTER TABLE procurements
        DROP COLUMN geographic_scope;
        """
    )