"""Test the flake8 plugin integration."""

import subprocess
import sys
from pathlib import Path


def test_flake8_plugin_detects_hash_comment_via_subprocess(tmp_path: Path):
    """Verify that flake8, when run as a subprocess, detects a hash comment.

    This test ensures that the plugin is correctly installed and discovered by
    flake8 via its entry point, and that it correctly identifies a violation
    in a controlled environment.

    Args:
        tmp_path: A pytest fixture providing a temporary directory path.
    """
    # Arrange: Create a temporary python file with a failing comment
    test_file = tmp_path / "test_file.py"
    test_file.write_text("my_variable = 1  # This should fail\n")

    # Act: Run flake8 as a subprocess on the temporary file
    process = subprocess.run(
        [sys.executable, "-m", "flake8", str(test_file)],
        capture_output=True,
        text=True,
    )

    # Assert: Check that flake8 exited with an error and reported our code
    assert process.returncode != 0, (
        "flake8 should exit with a non-zero status code. "
        f"stdout:\n{process.stdout}\nstderr:\n{process.stderr}"
    )
    assert "NHC9001" in process.stdout, (
        "The custom error NHC9001 should be in the output. "
        f"stdout:\n{process.stdout}"
    )
