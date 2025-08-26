import os


def get_table_name(base_table_name: str) -> str:
    """
    Returns the table name with the schema prefix if it exists.
    """
    schema_name = os.getenv("POSTGRES_DB_SCHEMA")
    if schema_name:
        return f"{schema_name}.{base_table_name}"
    return base_table_name
