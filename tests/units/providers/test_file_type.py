"""This module contains unit tests for the FileTypeProvider."""

from unittest.mock import MagicMock, patch

import pytest
from public_detective.providers.file_type import FileTypeProvider


@pytest.fixture
def file_type_provider() -> FileTypeProvider:
    """Returns a FileTypeProvider instance for testing."""
    return FileTypeProvider()


@pytest.mark.parametrize(
    ("mime_type", "expected_extension"),
    [
        ("application/pdf", ".pdf"),
        (
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".docx",
        ),
        ("application/msword", ".doc"),
        ("application/vnd.oasis.opendocument.text", ".odt"),
        ("application/rtf", ".rtf"),
        (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            ".xlsx",
        ),
        ("application/vnd.ms-excel", ".xls"),
        ("application/vnd.ms-excel.sheet.binary.macroenabled.12", ".xlsb"),
        ("application/vnd.oasis.opendocument.spreadsheet", ".ods"),
        ("text/csv", ".csv"),
        ("text/plain", ".txt"),
        ("video/mp4", ".mp4"),
        ("video/quicktime", ".mov"),
        ("video/x-msvideo", ".avi"),
        ("video/x-matroska", ".mkv"),
        ("audio/mpeg", ".mp3"),
        ("audio/wav", ".wav"),
        ("audio/x-flac", ".flac"),
        ("audio/ogg", ".ogg"),
        ("image/jpeg", ".jpeg"),
        ("image/png", ".png"),
        ("image/gif", ".gif"),
        ("image/bmp", ".bmp"),
        ("text/html", ".html"),
        ("application/xml", ".xml"),
        ("application/json", ".json"),
        ("text/markdown", ".md"),
    ],
)
@patch("magic.from_buffer")
def test_infer_extension_known_types(
    mock_from_buffer: MagicMock,
    file_type_provider: FileTypeProvider,
    mime_type: str,
    expected_extension: str,
) -> None:
    """Tests that known MIME types are correctly mapped to extensions."""
    mock_from_buffer.return_value = mime_type
    content = b"binary content"
    assert file_type_provider.infer_extension(content) == expected_extension


@patch("magic.from_buffer")
def test_infer_extension_unknown(mock_from_buffer: MagicMock, file_type_provider: FileTypeProvider) -> None:
    """Tests that an unknown file type returns None."""
    mock_from_buffer.return_value = "application/octet-stream"
    content = b"some random content"
    assert file_type_provider.infer_extension(content) is None


@patch("magic.from_buffer", side_effect=RuntimeError("unable to detect"))
def test_infer_extension_logs_error(mock_from_buffer: MagicMock, file_type_provider: FileTypeProvider) -> None:
    """Tests that an exception during detection is logged and returns None."""
    file_type_provider.logger = MagicMock()
    assert file_type_provider.infer_extension(b"some content") is None
    file_type_provider.logger.error.assert_called_once()
    logged_message = file_type_provider.logger.error.call_args[0][0]
    assert "Failed to infer file type" in logged_message
