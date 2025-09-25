"""This module contains the unit tests for the ConverterService."""

from unittest.mock import patch

import pytest
from public_detective.services.converter import ConverterService


def test_doc_to_pdf() -> None:
    """Test the doc_to_pdf method."""
    service = ConverterService()
    with patch.object(service, "_run_libreoffice_conversion") as mock_run:
        mock_run.return_value = [("output.pdf", b"pdf content")]
        result = service.doc_to_pdf(b"doc content", ".doc")
        assert result == b"pdf content"
        mock_run.assert_called_once_with(b"doc content", ".doc", "pdf")


def test_spreadsheet_to_csvs() -> None:
    """Test the spreadsheet_to_csvs method."""
    service = ConverterService()
    with patch.object(service, "_run_libreoffice_conversion") as mock_run:
        mock_run.return_value = [
            ("input_Sheet1.csv", b"csv content 1"),
            ("input_Sheet2.csv", b"csv content 2"),
        ]
        result = service.spreadsheet_to_csvs(b"xls content", ".xls")
        assert len(result) == 2
        assert result[0] == ("Sheet1.csv", b"csv content 1")
        assert result[1] == ("Sheet2.csv", b"csv content 2")
        mock_run.assert_called_once_with(
            b"xls content", ".xls", "csv:Text - txt - csv (StarCalc):44,34,76,1,,1031,true,true,true"
        )


def test_spreadsheet_to_csvs_single_sheet() -> None:
    """Test the spreadsheet_to_csvs method with a single sheet."""
    service = ConverterService()
    with patch.object(service, "_run_libreoffice_conversion") as mock_run:
        mock_run.return_value = [("input.csv", b"csv content 1")]
        result = service.spreadsheet_to_csvs(b"xls content", ".xls")
        assert len(result) == 1
        assert result[0] == ("input.csv", b"csv content 1")


def test_doc_to_pdf_no_output() -> None:
    """Test that doc_to_pdf raises an error if no output is produced."""
    service = ConverterService()
    with patch.object(service, "_run_libreoffice_conversion", return_value=[]):
        with pytest.raises(IndexError):
            service.doc_to_pdf(b"content", ".doc")


def test_spreadsheet_to_csvs_no_output() -> None:
    """Test that spreadsheet_to_csvs raises an error if no output is produced."""
    service = ConverterService()
    with patch.object(service, "_run_libreoffice_conversion", return_value=[]):
        result = service.spreadsheet_to_csvs(b"content", ".xls")
        assert result == []
