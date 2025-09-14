"""
Tests for the JSON schema of the analysis models, ensuring Gemini API compatibility.
"""

from typing import Any


def _recursively_check_for_key(data: Any, key_to_find: str) -> list[list]:
    """Recursively searches for a key in a nested dictionary.

    Args:
        data: The dictionary or list to search through.
        key_to_find: The key to search for.

    Returns:
        A list of paths to the found key.
    """
    paths = []
    if isinstance(data, dict):
        if key_to_find in data:
            paths.append([key_to_find])
        for key, value in data.items():
            sub_paths = _recursively_check_for_key(value, key_to_find)
            for sub_path in sub_paths:
                paths.append([key] + sub_path)
    elif isinstance(data, list):
        for index, item in enumerate(data):
            sub_paths = _recursively_check_for_key(item, key_to_find)
            for sub_path in sub_paths:
                paths.append([index] + sub_path)
    return paths
