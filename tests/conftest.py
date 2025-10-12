import pytest
from _pytest.nodes import Item


def pytest_collection_modifyitems(items: list[Item]) -> None:
    """Dynamically adds markers to tests based on their file path.

    Args:
        items: A list of test items collected by pytest.
    """
    for item in items:
        if "units" in item.path.parts:
            item.add_marker(pytest.mark.unit)
        elif "integrations" in item.path.parts:
            item.add_marker(pytest.mark.integration)
        elif "e2e" in item.path.parts:
            item.add_marker(pytest.mark.e2e)
