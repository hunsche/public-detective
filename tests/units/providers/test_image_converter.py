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


def test_to_png_no_output_file() -> None:
    """Tests that to_png raises RuntimeError when output file is not created."""
    provider = ImageConverterProvider()
    content = b"fake image content"
    extension = ".ai"

    # Mock _run_convert to succeed but not create the output file
    def mock_run_convert(_input_path: Path, _output_path: Path) -> None:
        # Do nothing - simulates successful conversion but no output file
        pass

    with patch.object(provider, "_run_convert", side_effect=mock_run_convert):
        with pytest.raises(RuntimeError, match="ImageMagick conversion failed to produce a PNG file"):
            provider.to_png(content, extension)


@patch("subprocess.run")
def test_run_convert_success_logging(mock_subprocess_run: Mock) -> None:
    """Tests that _run_convert logs success output."""
    mock_subprocess_run.return_value = Mock(returncode=0, stdout="conversion successful", stderr="")
    provider = ImageConverterProvider()

    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as td:
        tmp_dir = Path(td)
        in_path = tmp_dir / "input.ai"
        out_path = tmp_dir / "output.png"
        in_path.write_bytes(b"fake content")

        # This should not raise and should log success
        provider._run_convert(in_path, out_path)

    mock_subprocess_run.assert_called_once()
