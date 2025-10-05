"""Tests for the progress bar policy."""

import os
from unittest.mock import patch

import pytest
from public_detective.cli.analysis import should_show_progress


@pytest.mark.parametrize(
    "ci, isatty, flag, expected",
    [
        ("0", True, False, True),
        ("0", True, True, False),
        ("1", True, False, False),
        ("0", False, False, False),
    ],
)
def test_should_show_progress(ci: str, isatty: bool, flag: bool, expected: bool) -> None:
    """Tests the should_show_progress function."""
    env = os.environ.copy()
    env["CI"] = ci
    with patch("sys.stderr.isatty", return_value=isatty), patch.dict(os.environ, env, clear=False):
        assert should_show_progress(flag) is expected
