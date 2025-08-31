import os


def get_qualified_name(base_name: str) -> str:
    """
    Returns the object name with the schema prefix if it exists.
    """
    schema_name = os.getenv("POSTGRES_DB_SCHEMA")
    if schema_name:
        return f"{schema_name}.{base_name}"
    return base_name
