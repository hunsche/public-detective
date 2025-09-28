import runpy
from unittest.mock import patch


@patch("click.Group.main")
def test_main_execution_dunder(mock_main):
    """Tests that the main CLI function is called when the module is run as a script."""
    runpy.run_module("source.public_detective.cli.__main__", run_name="__main__")
    mock_main.assert_called_once()