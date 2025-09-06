import pytest
from sqlalchemy import text
from sqlalchemy.engine import Engine


@pytest.mark.timeout(180)
def test_all_primary_keys_are_uuid(db_session: Engine) -> None:
    """Tests that all primary keys in the database are of type UUID.

    Args:
        db_session: The SQLAlchemy engine instance from the db_session fixture.
    """
    with db_session.connect() as connection:
        # Get all tables in the current schema
        tables_query = text(
            """
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = :schema
            """
        )
        schema = connection.execute(text("SELECT current_schema()")).scalar_one()
        tables = connection.execute(tables_query, {"schema": schema}).fetchall()
        table_names = [table[0] for table in tables]

        for table_name in table_names:
            if table_name == "alembic_version":
                continue
            # Get the primary key column for the table
            # The following query is safe because the schema and table_name are
            # retrieved from the database metadata and not from user input.
            pk_query = text(
                f"""
                SELECT a.attname
                FROM   pg_index i
                JOIN   pg_attribute a ON a.attrelid = i.indrelid
                                   AND a.attnum = ANY(i.indkey)
                WHERE  i.indrelid = '"{schema}"."{table_name}"'::regclass
                AND    i.indisprimary;
            """  # nosec B608
            )
            pk_result = connection.execute(pk_query).fetchone()
            if not pk_result:
                continue  # Skip tables with no primary key

            pk_column_name = pk_result[0]

            # Check the data type of the primary key column
            pk_type_query = text(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_schema = :schema
                AND table_name = :table
                AND column_name = :column
                """
            )
            pk_type = connection.execute(
                pk_type_query,
                {
                    "schema": schema,
                    "table": table_name,
                    "column": pk_column_name,
                },
            ).scalar_one()

            assert pk_type == "uuid", f"Primary key of table '{table_name}' is not of type UUID, but '{pk_type}'"
