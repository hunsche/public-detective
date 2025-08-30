import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        if "units" in item.path.parts:
            item.add_marker(pytest.mark.unit)
        elif "integrations" in item.path.parts:
            item.add_marker(pytest.mark.integration)
