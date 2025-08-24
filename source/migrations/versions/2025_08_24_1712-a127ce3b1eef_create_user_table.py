from collections.abc import Sequence

from alembic import op

revision: str = "a127ce3b1eef"
down_revision: str | None = "ce0a16ca8b96"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE users (
            id SERIAL PRIMARY KEY,
            name VARCHAR(255) NOT NULL,
            age INTEGER
        );
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE users;")
