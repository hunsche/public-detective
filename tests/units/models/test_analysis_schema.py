"""
Tests for the JSON schema of the analysis models, ensuring Gemini API compatibility.
"""

import pytest
from models.analysis import Analysis, RedFlag
from pydantic import BaseModel


def _recursively_check_for_key(data, key_to_find):
    """
    Recursively searches for a key in a nested dictionary.
    Returns a list of paths to the found key.
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


@pytest.mark.parametrize(
    "model_class",
    [Analysis, RedFlag],
)
def test_no_default_key_in_model_schemas(model_class):
    """
    Ensures that the generated JSON schema for models sent to the Gemini API
    does not contain the 'default' key, which is not supported.
    """
    schema = model_class.model_json_schema()
    found_paths = _recursively_check_for_key(schema, "default")

    assert not found_paths, f"Forbidden 'default' key found in {model_class.__name__} schema at paths:\n" + "\n".join(
        " -> ".join(map(str, p)) for p in found_paths
    )


def test_detection_logic_is_effective_control_test():
    """
    Control test to prove that the detection logic correctly finds a 'default'
    key when one is intentionally added to a model's schema.
    """

    class ModelWithDefault(BaseModel):
        """A temporary model for this test."""

        fake_field: str = "default_value"

    schema = ModelWithDefault.model_json_schema()
    found_paths = _recursively_check_for_key(schema, "default")

    assert found_paths, "The 'default' key was not found, indicating the detection logic is flawed."

    # Further validation to ensure it's the correct key
    path_str = " -> ".join(map(str, found_paths[0]))
    assert (
        path_str == "properties -> fake_field -> default"
    ), "The 'default' key was found, but not at the expected path for 'fake_field'."
