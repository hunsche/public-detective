"""This module provides utilities for handling sensitive information."""

SECRET_KEYWORDS = [
    "TOKEN",
    "SECRET",
    "PASS",
    "PWD",
    "CREDENTIAL",
    "API_KEY",
    "CLIENT_SECRET",
    "PRIVATE_KEY",
    "GCP_SERVICE_ACCOUNT_CREDENTIALS",
]


def is_secret_key(key: str) -> bool:
    """Checks if a key name suggests it's a secret.

    Args:
        key: The key name to check.

    Returns:
        True if the key likely holds a secret, False otherwise.
    """
    key_upper = key.upper()
    return any(keyword in key_upper for keyword in SECRET_KEYWORDS)


def mask_value(value: str | None) -> str:
    """Masks a secret value, showing only the last 4 characters.

    Args:
        value: The value to mask.

    Returns:
        The masked value.
    """
    if value is None:
        return "Not set"
    if len(value) < 4:
        return "****"
    return f"•••••••••••••••••••• (last 4: {value[-4:]})"
