import os

from sqlalchemy import text
from sqlalchemy.engine import Engine


def test_inspect_database(db_session: Engine) -> None:
    """
    This test connects to the database and prints the contents of the tables.
    """
    with db_session.connect() as connection:
        connection.execute(text(f"SET search_path TO {os.environ['POSTGRES_DB_SCHEMA']}"))
        tables = connection.execute(
            text("SELECT tablename FROM pg_tables WHERE schemaname = 'public'")
        ).fetchall()
        for table in tables:
            table_name = table[0]
            print(f"--- Contents of table: {table_name} ---")
            rows = connection.execute(text(f"SELECT * FROM {table_name}")).fetchall()
            for row in rows:
                print(row)
