"""
create_votes_table_and_add_votes_count_to_procurement_analyses
"""

from collections.abc import Sequence

from alembic import op

from source.migrations.helpers import get_qualified_name

# revision identifiers, used by Alembic.
revision: str = "130661653c2d"
down_revision: str | None = "9594c79c1cd3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    procurement_analyses_table = get_qualified_name("procurement_analyses")
    votes_table = get_qualified_name("votes")

    op.execute(
        f"""
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'vote_type') THEN
                CREATE TYPE vote_type AS ENUM ('UP', 'DOWN');
            END IF;
        END$$;

        CREATE TABLE {votes_table} (
            vote_id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            analysis_id UUID NOT NULL REFERENCES {procurement_analyses_table}(analysis_id),
            user_id UUID NOT NULL,
            vote_type vote_type NOT NULL,
            UNIQUE (analysis_id, user_id)
        );

        ALTER TABLE {procurement_analyses_table}
        ADD COLUMN votes_count INTEGER NOT NULL DEFAULT 0;

        CREATE INDEX idx_votes_analysis_id ON {votes_table} (analysis_id);
        """
    )


def downgrade() -> None:
    procurement_analyses_table = get_qualified_name("procurement_analyses")
    votes_table = get_qualified_name("votes")

    op.execute(
        f"""
        DROP TABLE IF EXISTS {votes_table};
        DROP TYPE IF EXISTS vote_type;
        ALTER TABLE {procurement_analyses_table}
        DROP COLUMN IF EXISTS votes_count;
        """
    )
