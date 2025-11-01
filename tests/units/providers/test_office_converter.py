from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from public_detective.providers.office_converter import OfficeConverterProvider


@patch("subprocess.run")
@patch("pathlib.Path.write_bytes")
@patch("pathlib.Path.read_bytes")
def test_to_pdf_success(
    mock_read_bytes: MagicMock,
    _mock_write_bytes: MagicMock,
    mock_run: MagicMock,
) -> None:
    """Tests the to_pdf method for a successful conversion."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    mock_read_bytes.return_value = b"test"
    with patch("pathlib.Path.glob", return_value=[Path("test.pdf")]):
        provider = OfficeConverterProvider()
        pdf_content = provider.to_pdf(b"test", ".doc")
        assert pdf_content == b"test"


@patch("subprocess.run")
def test_to_pdf_failure(mock_run: MagicMock) -> None:
    """Tests the to_pdf method for a failed conversion."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")
    provider = OfficeConverterProvider()
    with pytest.raises(RuntimeError, match="LibreOffice failed"):
        provider.to_pdf(b"test", ".doc")


@patch("subprocess.run")
@patch("pathlib.Path.write_bytes")
@patch("pathlib.Path.read_bytes", return_value=b"spreadsheet pdf")
def test_to_pdf_spreadsheet_options(
    mock_read_bytes: MagicMock,
    _mock_write_bytes: MagicMock,
    mock_run: MagicMock,
) -> None:
    """Ensures spreadsheet conversions use the LibreOffice calc export filter."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    with patch("pathlib.Path.glob", return_value=[Path("test.pdf")]):
        provider = OfficeConverterProvider()
        provider.logger = MagicMock()
        result = provider.to_pdf(b"spreadsheet", ".xlsx")
        assert result == b"spreadsheet pdf"

    command = mock_run.call_args[0][0]
    convert_to_index = command.index("--convert-to") + 1
    assert "pdf:calc_pdf_Export" in command[convert_to_index]


@patch("subprocess.run")
def test_to_pdf_without_output_file(mock_run: MagicMock) -> None:
    """Raises an error when LibreOffice does not produce a PDF file."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    provider = OfficeConverterProvider()
    with patch("pathlib.Path.glob", return_value=[]):
        with pytest.raises(RuntimeError, match="failed to produce a PDF"):
            provider.to_pdf(b"test", ".doc")
