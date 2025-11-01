"""Add inferred_extension and used_fallback_conversion to file_records

Revision ID: 2a9a3b9f3e1b
Revises: 9594c79c1cd3
Create Date: 2025-10-27 05:11:27.362383

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = '2a9a3b9f3e1b'
down_revision: Union[str, None] = '9594c79c1cd3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE file_records
        ADD COLUMN inferred_extension VARCHAR(10),
        ADD COLUMN used_fallback_conversion BOOLEAN DEFAULT FALSE;
        """
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE file_records
        DROP COLUMN inferred_extension,
        DROP COLUMN used_fallback_conversion;
        """
    )
