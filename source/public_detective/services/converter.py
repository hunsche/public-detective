"""This module provides a service for converting files."""

import io
from typing import cast

import imageio
from PIL import Image
from public_detective.providers.logging import Logger, LoggingProvider
from public_detective.providers.office_converter import OfficeConverterProvider


class ConverterService:
    """A service for converting various file types for AI analysis."""

    logger: Logger
    office_converter: OfficeConverterProvider

    _CONVERTIBLE_TO_PDF = {
        ".docx",
        ".doc",
        ".odt",
        ".rtf",
        ".xlsx",
        ".xls",
        ".xlsb",
        ".ods",
        ".csv",
        ".html",
        ".xml",
        ".txt",
        ".md",
    }

    def __init__(self) -> None:
        """Initializes the service."""
        self.logger: Logger = LoggingProvider().get_logger()
        self.office_converter: OfficeConverterProvider = OfficeConverterProvider()

    def gif_to_mp4(self, gif_content: bytes) -> bytes:
        """Converts a GIF file content to an MP4 file content.

        Args:
            gif_content: The content of the GIF file.

        Returns:
            The content of the converted MP4 file.
        """
        self.logger.info("Converting GIF to MP4.")
        try:
            reader = imageio.get_reader(gif_content, format="gif")  # type: ignore[arg-type]
            fps = reader.get_meta_data().get("fps", 24)

            output_buffer = io.BytesIO()
            with imageio.get_writer(output_buffer, format="mp4", fps=fps) as writer:  # type: ignore[arg-type]
                for frame in reader:  # type: ignore[attr-defined]
                    writer.append_data(frame)  # type: ignore[attr-defined]

            return output_buffer.getvalue()
        except Exception as e:
            self.logger.error(f"GIF to MP4 conversion failed: {e}", exc_info=True)
            raise

    def bmp_to_png(self, bmp_content: bytes) -> bytes:
        """Converts a BMP file content to a PNG file content.

        Args:
            bmp_content: The content of the BMP file.

        Returns:
            The content of the converted PNG file.
        """
        self.logger.info("Converting BMP to PNG.")
        try:
            with Image.open(io.BytesIO(bmp_content)) as img:
                with io.BytesIO() as output_buffer:
                    img.save(output_buffer, format="PNG")
                    return output_buffer.getvalue()
        except Exception as e:
            self.logger.error(f"BMP to PNG conversion failed: {e}", exc_info=True)
            raise

    def is_supported_for_conversion(self, extension: str) -> bool:
        """Checks if a file extension is supported for conversion to PDF.

        Args:
            extension: The file extension (e.g., ".docx").

        Returns:
            True if the extension is supported, False otherwise.
        """
        return extension in self._CONVERTIBLE_TO_PDF

    def convert_to_pdf(self, file_content: bytes, original_extension: str) -> bytes:
        """Converts a file to PDF using LibreOffice.

        Args:
            file_content: The content of the file to convert.
            original_extension: The original extension of the file (e.g., ".docx").

        Returns:
            The content of the converted PDF file.
        """
        self.logger.info(f"Converting {original_extension} to PDF using LibreOffice.")
        return cast(bytes, self.office_converter.to_pdf(file_content, original_extension))

    def doc_to_pdf(self, doc_content: bytes) -> bytes:
        """Converts a DOC file content to a PDF file.

        Args:
            doc_content: The content of the DOC file.

        Returns:
            The content of the converted PDF file.
        """
        return self.convert_to_pdf(doc_content, ".doc")

    def docx_to_pdf(self, docx_content: bytes) -> bytes:
        """Converts a DOCX file content to a PDF file.

        Args:
            docx_content: The content of the DOCX file.

        Returns:
            The content of the converted PDF file.
        """
        return self.convert_to_pdf(docx_content, ".docx")

    def rtf_to_pdf(self, rtf_content: bytes) -> bytes:
        """Converts an RTF file content to a PDF file.

        Args:
            rtf_content: The content of the RTF file.

        Returns:
            The content of the converted PDF file.
        """
        return self.convert_to_pdf(rtf_content, ".rtf")

    def odt_to_pdf(self, odt_content: bytes) -> bytes:
        """Converts an ODT file content to a PDF file.

        Args:
            odt_content: The content of the ODT file.

        Returns:
            The content of the converted PDF file.
        """
        return self.convert_to_pdf(odt_content, ".odt")

    def xls_to_pdf(self, xls_content: bytes) -> bytes:
        """Converts an XLS file content to a PDF file.

        Args:
            xls_content: The content of the XLS file.

        Returns:
            The content of the converted PDF file.
        """
        return self.convert_to_pdf(xls_content, ".xls")

    def xlsx_to_pdf(self, xlsx_content: bytes) -> bytes:
        """Converts an XLSX file content to a PDF file.

        Args:
            xlsx_content: The content of the XLSX file.

        Returns:
            The content of the converted PDF file.
        """
        return self.convert_to_pdf(xlsx_content, ".xlsx")

    def xlsb_to_pdf(self, xlsb_content: bytes) -> bytes:
        """Converts an XLSB file content to a PDF file.

        Args:
            xlsb_content: The content of the XLSB file.

        Returns:
            The content of the converted PDF file.
        """
        return self.convert_to_pdf(xlsb_content, ".xlsb")

    def ods_to_pdf(self, ods_content: bytes) -> bytes:
        """Converts an ODS file content to a PDF file.

        Args:
            ods_content: The content of the ODS file.

        Returns:
            The content of the converted PDF file.
        """
        return self.convert_to_pdf(ods_content, ".ods")
