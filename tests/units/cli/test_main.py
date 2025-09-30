import subprocess  # nosec B404
import sys


def test_main_entrypoint() -> None:
    """
    Tests that the main entrypoint runs without errors.
    """
    result = subprocess.run(
        [sys.executable, "-m", "public_detective.cli"],  # nosec B603
        capture_output=True,
        text=True,
        check=False,
    )
    assert "Usage: python -m public_detective.cli" in result.stderr
