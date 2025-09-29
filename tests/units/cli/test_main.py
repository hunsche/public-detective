"""
Unit tests for the main CLI entrypoint.
"""

from unittest.mock import MagicMock, patch

from public_detective.cli import __main__


@patch("public_detective.cli.__main__.cli")
def test_main_entrypoint_call(mock_cli: MagicMock) -> None:
    """
    Tests that the main entrypoint function calls the cli group.
    """
    __main__.main()
    mock_cli.assert_called_once()
