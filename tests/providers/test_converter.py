"""
Unit tests for the ConverterProvider.
"""

import subprocess
from unittest.mock import MagicMock, patch

import pytest
from providers.converter import ConversionError, ConverterProvider


@patch("providers.converter.which", return_value="/usr/bin/libreoffice")
def test_converter_provider_instantiation_success(mock_which):
    """Tests that the ConverterProvider instantiates if LibreOffice is found."""
    provider = ConverterProvider()
    assert provider is not None
    mock_which.assert_called_once_with("libreoffice")


@patch("providers.converter.which", return_value=None)
def test_converter_provider_instantiation_failure(mock_which):
    """Tests that the ConverterProvider raises an error if LibreOffice is not found."""
    with pytest.raises(RuntimeError, match="LibreOffice not found"):
        ConverterProvider()
    mock_which.assert_called_once_with("libreoffice")


@patch("providers.converter.which", return_value="/usr/bin/libreoffice")
@patch("subprocess.run")
def test_convert_file_success(mock_subprocess_run, mock_which):
    """Tests a successful file conversion."""
    mock_process = MagicMock()
    mock_process.returncode = 0
    mock_subprocess_run.return_value = mock_process

    provider = ConverterProvider()

    with patch("os.path.exists", return_value=True), patch(
        "builtins.open", MagicMock()
    ):
        result = provider.convert_file(b"test content", "test.docx", "pdf")

    assert result is not None
    mock_subprocess_run.assert_called_once()


@patch("providers.converter.which", return_value="/usr/bin/libreoffice")
@patch("subprocess.run")
def test_convert_file_failure_return_code(mock_subprocess_run, mock_which):
    """Tests a file conversion that fails due to a non-zero return code."""
    mock_process = MagicMock()
    mock_process.returncode = 1
    mock_subprocess_run.return_value = mock_process

    provider = ConverterProvider()
    with pytest.raises(ConversionError, match="return code 1"):
        provider.convert_file(b"test content", "test.docx", "pdf")

    mock_subprocess_run.assert_called_once()
