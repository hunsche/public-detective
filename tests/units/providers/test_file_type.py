"""This module contains unit tests for the FileTypeProvider."""

import pytest
from public_detective.providers.file_type import FileTypeProvider


@pytest.fixture
def file_type_provider():
    """Returns a FileTypeProvider instance for testing."""
    return FileTypeProvider()


from unittest.mock import patch


@patch("magic.from_buffer")
def test_infer_extension_pdf(mock_from_buffer, file_type_provider):
    """Tests that a PDF file is correctly identified."""
    mock_from_buffer.return_value = "application/pdf"
    content = b"%PDF-1.4"
    assert file_type_provider.infer_extension(content) == ".pdf"


@patch("magic.from_buffer")
def test_infer_extension_docx(mock_from_buffer, file_type_provider):
    """Tests that a DOCX file is correctly identified."""
    mock_from_buffer.return_value = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    content = b"PK\x03\x04"
    assert file_type_provider.infer_extension(content) == ".docx"


@patch("magic.from_buffer")
def test_infer_extension_unknown(mock_from_buffer, file_type_provider):
    """Tests that an unknown file type returns None."""
    mock_from_buffer.return_value = "application/octet-stream"
    content = b"some random content"
    assert file_type_provider.infer_extension(content) is None
