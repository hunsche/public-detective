"""Unit tests for the flake8-no-hash-comments plugin."""

import ast
from collections.abc import Generator
from pathlib import Path

import pytest

from linting.local_linters.flake8_no_hash_comments import NoHashCommentsPlugin


def _run_linter(code: str, tmp_path: Path) -> list[str]:
    """Run the linter on a given code string by writing it to a temporary file."""
    test_file = tmp_path / "test.py"
    test_file.write_text(code)

    # The tree and lines are not strictly needed by our linter anymore,
    # but are required by the flake8 plugin constructor.
    tree = ast.parse("")
    lines: list[str] = []

    plugin = NoHashCommentsPlugin(tree=tree, filename=str(test_file), lines=lines)
    return [error[2] for error in plugin.run()]


@pytest.fixture(autouse=True)
def reset_plugin_config() -> Generator[None, None, None]:
    """A fixture to reset the plugin's configuration before and after each test."""
    original_prefixes = NoHashCommentsPlugin.allowed_prefixes
    original_substrings = NoHashCommentsPlugin.allowed_substrings

    NoHashCommentsPlugin.allowed_prefixes = []
    NoHashCommentsPlugin.allowed_substrings = []

    yield

    NoHashCommentsPlugin.allowed_prefixes = original_prefixes
    NoHashCommentsPlugin.allowed_substrings = original_substrings


# === Test Cases ===


def test_fails_on_full_line_comment(tmp_path: Path) -> None:
    """Verify that a standard full-line hash comment is detected."""
    code = "# This is a standard comment."
    errors = _run_linter(code, tmp_path)
    assert len(errors) == 1
    assert NoHashCommentsPlugin.NOHASH_ERROR_CODE in errors[0]


def test_fails_on_inline_comment(tmp_path: Path) -> None:
    """Verify that a standard inline hash comment is detected."""
    code = "a = 1  # This is an inline comment."
    errors = _run_linter(code, tmp_path)
    assert len(errors) == 1
    assert NoHashCommentsPlugin.NOHASH_ERROR_CODE in errors[0]


def test_allows_configured_prefix(tmp_path: Path) -> None:
    """Verify that a comment with a configured prefix is allowed."""
    NoHashCommentsPlugin.allowed_prefixes = ["Arrange"]
    code = "# Arrange: Set up the test data."
    errors = _run_linter(code, tmp_path)
    assert len(errors) == 0


def test_allows_configured_substring(tmp_path: Path) -> None:
    """Verify that a comment with a configured substring is allowed."""
    NoHashCommentsPlugin.allowed_substrings = ["nosec"]
    code = "password = '123'  # nosec B105"
    errors = _run_linter(code, tmp_path)
    assert len(errors) == 0


def test_allows_shebang_and_coding(tmp_path: Path) -> None:
    """Verify that shebang and coding declarations are always allowed."""
    code = """#!/usr/bin/env python
# -*- coding: utf-8 -*-"""
    errors = _run_linter(code, tmp_path)
    assert len(errors) == 0


def test_ignores_hash_in_string(tmp_path: Path) -> None:
    """Verify that a '#' character inside a string is not flagged."""
    code = 'url = "http://example.com/page#anchor"'
    errors = _run_linter(code, tmp_path)
    assert len(errors) == 0


def test_allows_type_ignore_substring(tmp_path: Path) -> None:
    """Verify that a comment with 'type: ignore' is allowed."""
    NoHashCommentsPlugin.allowed_substrings = ["type: ignore"]
    code = "x = my_function()  # type: ignore[attr-defined]"
    errors = _run_linter(code, tmp_path)
    assert len(errors) == 0


def test_allows_noqa_substring(tmp_path: Path) -> None:
    """Verify that a comment with 'noqa' is allowed."""
    NoHashCommentsPlugin.allowed_substrings = ["noqa"]
    code = "import os  # noqa: F401"
    errors = _run_linter(code, tmp_path)
    assert len(errors) == 0
