import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from public_detective.providers.office_converter import OfficeConverterProvider


@patch("subprocess.run")
@patch("pathlib.Path.write_bytes")
@patch("pathlib.Path.read_bytes")
def test_to_pdf_success(mock_read_bytes, mock_write_bytes, mock_run):
    """Tests the to_pdf method for a successful conversion."""
    mock_run.return_value = MagicMock(returncode=0, stdout="OK", stderr="")
    mock_read_bytes.return_value = b"test"
    with patch("pathlib.Path.glob", return_value=[Path("test.pdf")]):
        provider = OfficeConverterProvider()
        pdf_content = provider.to_pdf(b"test", ".doc")
        assert pdf_content is not None


@patch("subprocess.run")
def test_to_pdf_failure(mock_run):
    """Tests the to_pdf method for a failed conversion."""
    mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Error")
    provider = OfficeConverterProvider()
    with pytest.raises(RuntimeError):
        provider.to_pdf(b"test", ".doc")
