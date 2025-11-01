"""This module provides a service for identifying file types."""

import magic
from public_detective.providers.logging import Logger, LoggingProvider


class FileTypeProvider:
    """A provider for inferring file types from their content."""

    def __init__(self) -> None:
        """Initializes the FileTypeProvider."""
        self.logger: Logger = LoggingProvider().get_logger()

    def infer_extension(self, content: bytes) -> str | None:
        """Infers the file extension from its content.

        Args:
            content: The byte content of the file.

        Returns:
            The inferred file extension (e.g., ".pdf"), or None if the
            type could not be determined.
        """
        try:
            mime_type = magic.from_buffer(content, mime=True)
            extension = self._get_extension_from_mime(mime_type)
            if extension:
                return f".{extension}"
            return None
        except Exception as e:
            self.logger.error(f"Failed to infer file type: {e}", exc_info=True)
            return None

    def _get_extension_from_mime(self, mime_type: str) -> str | None:  # noqa: C901
        """Maps a MIME type to a file extension.

        This is not an exhaustive list but covers common types relevant
        to this project.

        Args:
            mime_type: The MIME type string.

        Returns:
            A file extension string, or None if no mapping is found.
        """
        if mime_type == "application/pdf":
            return "pdf"
        if mime_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
            return "docx"
        if mime_type == "application/msword":
            return "doc"
        if mime_type == "application/vnd.oasis.opendocument.text":
            return "odt"
        if mime_type == "application/rtf":
            return "rtf"
        if mime_type == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet":
            return "xlsx"
        if mime_type == "application/vnd.ms-excel":
            return "xls"
        if mime_type == "application/vnd.ms-excel.sheet.binary.macroenabled.12":
            return "xlsb"
        if mime_type == "application/vnd.oasis.opendocument.spreadsheet":
            return "ods"
        if mime_type == "text/csv":
            return "csv"
        if mime_type == "text/plain":
            return "txt"
        if mime_type == "video/mp4":
            return "mp4"
        if mime_type == "video/quicktime":
            return "mov"
        if mime_type == "video/x-msvideo":
            return "avi"
        if mime_type == "video/x-matroska":
            return "mkv"
        if mime_type == "audio/mpeg":
            return "mp3"
        if mime_type == "audio/wav":
            return "wav"
        if mime_type == "audio/x-flac":
            return "flac"
        if mime_type == "audio/ogg":
            return "ogg"
        if mime_type == "image/jpeg":
            return "jpeg"
        if mime_type == "image/png":
            return "png"
        if mime_type == "image/gif":
            return "gif"
        if mime_type == "image/bmp":
            return "bmp"
        if mime_type == "text/html":
            return "html"
        if mime_type == "application/xml":
            return "xml"
        if mime_type == "application/json":
            return "json"
        if mime_type == "text/markdown":
            return "md"
        return None
