"""This module provides a service for converting files."""

import csv
import io
import os
import subprocess
import tempfile
from pathlib import Path

from openpyxl import load_workbook

from public_detective.providers.logging import Logger, LoggingProvider


class ConverterService:
    """A service for converting various file types for AI analysis."""

    def __init__(self) -> None:
        """Initializes the service."""
        self.logger: Logger = LoggingProvider().get_logger()

    def _run_libreoffice_conversion(self, input_content: bytes, input_ext: str) -> bytes:
        """Converts a file to PDF using LibreOffice in headless mode."""
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / f"input{input_ext}"
            input_path.write_bytes(input_content)

            self.logger.info(f"Running LibreOffice conversion for {input_path}")
            command = [
                "soffice",
                "--headless",
                "--convert-to",
                "pdf",
                "--outdir",
                temp_dir,
                str(input_path),
            ]
            process = subprocess.run(
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            self.logger.info(f"LibreOffice stdout: {process.stdout}")
            if process.stderr:
                self.logger.warning(f"LibreOffice stderr: {process.stderr}")

            output_path = Path(temp_dir) / "input.pdf"
            if not output_path.exists():
                raise FileNotFoundError(f"Converted PDF file not found at {output_path}")

            return output_path.read_bytes()

    def docx_to_pdf(self, docx_content: bytes) -> bytes:
        """Converts a DOCX file content to a PDF file content."""
        self.logger.info("Converting DOCX to PDF.")
        return self._run_libreoffice_conversion(docx_content, ".docx")

    def xlsx_to_csv(self, xlsx_content: bytes) -> bytes:
        """Converts an XLSX file content to a CSV file content in-memory."""
        self.logger.info("Converting XLSX to CSV.")
        try:
            workbook = load_workbook(filename=io.BytesIO(xlsx_content))
            # For simplicity, we'll process the first sheet only.
            sheet = workbook.active

            output = io.StringIO()
            writer = csv.writer(output)

            for row in sheet.iter_rows():
                writer.writerow([cell.value for cell in row])

            # The csv module writes to a StringIO, which is text.
            # We need to return bytes, so we encode it.
            return output.getvalue().encode("utf-8")
        except Exception as e:
            self.logger.error(f"Failed to convert XLSX to CSV: {e}", exc_info=True)
            raise
