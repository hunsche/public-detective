"""Unit tests for the ImageConverterProvider."""

from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from public_detective.providers.image_converter import ImageConverterProvider


def test_to_png_success() -> None:
    """Tests that the to_png method successfully converts a file."""
    provider = ImageConverterProvider()
    content = b"fake image content"
    extension = ".ai"

    def mock_run_convert(_input_path: Path, output_path: Path) -> None:
        output_path.write_bytes(b"fake png content")

    with patch.object(provider, "_run_convert", side_effect=mock_run_convert):
        result = provider.to_png(content, extension)

    assert result == b"fake png content"


@patch("subprocess.run")
def test_to_png_failure(mock_subprocess_run: Mock) -> None:
    """Tests that the to_png method raises an exception when conversion fails."""
    mock_subprocess_run.return_value = Mock(returncode=1, stdout="", stderr="conversion failed")
    provider = ImageConverterProvider()
    content = b"fake image content"
    extension = ".ai"

    with pytest.raises(RuntimeError):
        provider.to_png(content, extension)

    mock_subprocess_run.assert_called_once()
