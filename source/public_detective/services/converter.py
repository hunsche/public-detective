"""This module provides a service for converting files."""

import os
import re
import subprocess  # nosec B404
import tempfile
from pathlib import Path

from public_detective.providers.logging import Logger, LoggingProvider


class ConverterService:
    """A service for converting various file types for AI analysis."""

    def __init__(self) -> None:
        """Initializes the service."""
        self.logger: Logger = LoggingProvider().get_logger()

    def _run_libreoffice_conversion(
        self, input_content: bytes, input_ext: str, output_filter: str
    ) -> list[tuple[str, bytes]]:  # pragma: no cover
        """Converts a file using LibreOffice, handling multiple output files.

        Args:
            input_content: The content of the file to convert.
            input_ext: The extension of the input file.
            output_filter: The output filter to use for the conversion.

        Returns:
            A list of tuples containing the output filename and content.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = Path(temp_dir) / f"input{input_ext}"
            input_path.write_bytes(input_content)

            self.logger.info(f"Running LibreOffice conversion for {input_path} with filter {output_filter}")
            command = [
                "soffice",
                "--headless",
                "--convert-to",
                output_filter,
                "--outdir",
                temp_dir,
                str(input_path),
            ]
            process = subprocess.run(  # nosec B603
                command,
                capture_output=True,
                text=True,
                check=True,
                timeout=60,
            )
            self.logger.info(f"LibreOffice stdout: {process.stdout}")
            if process.stderr:
                self.logger.warning(f"LibreOffice stderr: {process.stderr}")

            output_files = []
            for item in os.listdir(temp_dir):
                if item != input_path.name:
                    output_path = Path(temp_dir) / item
                    output_files.append((item, output_path.read_bytes()))

            if not output_files:
                raise FileNotFoundError("Conversion did not produce any output files.")

            return output_files

    def doc_to_pdf(self, doc_content: bytes, original_extension: str) -> bytes:
        """Converts a DOC or DOCX file content to a PDF file content.

        Args:
            doc_content: The content of the DOC or DOCX file.
            original_extension: The original extension of the file.

        Returns:
            The content of the converted PDF file.
        """
        self.logger.info(f"Converting {original_extension} to PDF.")
        output_files = self._run_libreoffice_conversion(doc_content, original_extension, "pdf")
        return output_files[0][1]

    def spreadsheet_to_csvs(self, xls_content: bytes, original_extension: str) -> list[tuple[str, bytes]]:
        """Converts an XLSX or XLS file to one or more CSV files (one per sheet).

        Args:
            xls_content: The content of the XLSX or XLS file.
            original_extension: The original extension of the file.

        Returns:
            A list of tuples containing the sheet name and the content of the converted CSV file.
        """
        self.logger.info(f"Converting {original_extension} to CSV(s).")
        csv_filter = "csv:Text - txt - csv (StarCalc):44,34,76,1,,1031,true,true,true"
        output_files = self._run_libreoffice_conversion(xls_content, original_extension, csv_filter)

        sanitized_files = []
        for filename, content in output_files:
            match = re.search(r"input_(.+)\.csv", filename)
            if match:
                sheet_name = match.group(1)
                sanitized_name = f"{sheet_name}.csv"
                sanitized_files.append((sanitized_name, content))
            else:
                sanitized_files.append((filename, content))

        return sanitized_files
