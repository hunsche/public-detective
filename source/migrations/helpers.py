import os


def get_qualified_name(base_name: str) -> str:
    """Returns the object name with the schema prefix if it exists.

    Args:
        base_name: The base name of the object.

    Returns:
        The qualified name with schema prefix if it exists, otherwise the base name.
    """
    schema_name = os.getenv("POSTGRES_DB_SCHEMA")
    if schema_name:
        return f"{schema_name}.{base_name}"
    return base_name
