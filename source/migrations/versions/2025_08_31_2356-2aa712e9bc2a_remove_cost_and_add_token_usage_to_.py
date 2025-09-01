"""Remove cost and add token usage to analyses

Revision ID: 2aa712e9bc2a
Revises: b7179b0a29e7
Create Date: 2025-08-31 16:56:14.930495

"""

from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_qualified_name

# revision identifiers, used by Alembic.
revision: str = "2aa712e9bc2a"
down_revision: str | None = "b7179b0a29e7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    procurement_analyses_table = get_qualified_name("procurement_analyses")
    op.execute(
        f"""
        ALTER TABLE {procurement_analyses_table}
        ADD COLUMN input_tokens_used INTEGER,
        ADD COLUMN output_tokens_used INTEGER;
    """
    )
    op.execute(
        f"""
        ALTER TABLE {procurement_analyses_table}
        RENAME COLUMN estimated_cost TO estimated_cost_dropped;
    """
    )


def downgrade() -> None:
    procurement_analyses_table = get_qualified_name("procurement_analyses")
    op.execute(
        f"""
        ALTER TABLE {procurement_analyses_table}
        RENAME COLUMN estimated_cost_dropped TO estimated_cost;
    """
    )
    op.execute(
        f"""
        ALTER TABLE {procurement_analyses_table}
        DROP COLUMN input_tokens_used,
        DROP COLUMN output_tokens_used;
    """
    )
