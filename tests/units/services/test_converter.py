from unittest.mock import MagicMock, patch

import pytest
from public_detective.services.converter import ConverterService


@patch("mammoth.convert_to_html")
def test_docx_to_html_success(mock_convert):
    """Tests the docx_to_html method for a successful conversion."""
    mock_convert.return_value = MagicMock(value="<p>test</p>")
    service = ConverterService()
    html = service.docx_to_html(b"test")
    assert html == "<p>test</p>"


@patch("mammoth.convert_to_html")
@patch("public_detective.providers.office_converter.OfficeConverterProvider.to_pdf")
@patch("textract.process")
def test_docx_to_html_fallback(mock_process, mock_to_pdf, mock_convert):
    """Tests the docx_to_html method for a failed conversion and successful fallback."""
    mock_convert.side_effect = Exception("test")
    mock_to_pdf.return_value = b"test"
    mock_process.return_value = b"test"
    service = ConverterService()
    html = service.docx_to_html(b"test")
    assert html == "test"


@patch("textract.process")
def test_doc_to_text_success(mock_process):
    """Tests the doc_to_text method for a successful conversion."""
    mock_process.return_value = b"test"
    service = ConverterService()
    text = service.doc_to_text(b"test")
    assert text == "test"


@patch("textract.process")
@patch("public_detective.providers.office_converter.OfficeConverterProvider.to_pdf")
def test_doc_to_text_fallback(mock_to_pdf, mock_process):
    """Tests the doc_to_text method for a failed conversion and successful fallback."""
    mock_process.side_effect = Exception("test")
    mock_to_pdf.return_value = b"test"
    service = ConverterService()
    # Create a new mock for the second textract call
    with patch("textract.process") as mock_process_2:
        mock_process_2.return_value = b"test"
        text = service.doc_to_text(b"test")
        assert text == "test"


@patch("striprtf.striprtf.rtf_to_text")
def test_rtf_to_text_success(mock_rtf_to_text):
    """Tests the rtf_to_text method for a successful conversion."""
    mock_rtf_to_text.return_value = "test"
    service = ConverterService()
    text = service.rtf_to_text(b"test")
    assert text == "test"


@patch("striprtf.striprtf.rtf_to_text")
@patch("public_detective.providers.office_converter.OfficeConverterProvider.to_pdf")
@patch("textract.process")
def test_rtf_to_text_fallback(mock_process, mock_to_pdf, mock_rtf_to_text):
    """Tests the rtf_to_text method for a failed conversion and successful fallback."""
    mock_rtf_to_text.side_effect = Exception("test")
    mock_to_pdf.return_value = b"test"
    mock_process.return_value = b"test"
    service = ConverterService()
    text = service.rtf_to_text(b"test")
    assert text == "test"
