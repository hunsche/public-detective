"""Providers for converting office documents with LibreOffice."""

import json
import subprocess  # nosec B404
import tempfile
from pathlib import Path

from public_detective.providers.logging import Logger, LoggingProvider


class OfficeConverterProvider:
    """A provider for converting office files using LibreOffice."""

    logger: Logger
    _SPREADSHEET_EXTENSIONS: tuple[str, ...] = (".xlsx", ".xls", ".xlsb", ".ods", ".xlsm")

    def __init__(self) -> None:
        """Initializes the provider."""
        self.logger = LoggingProvider().get_logger()

    def to_pdf(self, file_content: bytes, original_extension: str) -> bytes:
        """Converts an office file to PDF.

        Args:
            file_content: The content of the file to convert.
            original_extension: The original extension of the file.

        Returns:
            The content of the converted PDF file.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp_dir = Path(td)
            in_path = tmp_dir / f"input{original_extension}"
            in_path.write_bytes(file_content)

            is_spreadsheet = original_extension.lower() in self._SPREADSHEET_EXTENSIONS
            self._run_soffice(in_path, tmp_dir, is_spreadsheet=is_spreadsheet)

            produced_files = list(tmp_dir.glob("*.pdf"))
            if not produced_files:
                raise RuntimeError("LibreOffice conversion failed to produce a PDF file.")

            out_file = produced_files[0]
            return out_file.read_bytes()

    def _run_soffice(
        self,
        input_path: Path,
        output_dir: Path,
        is_spreadsheet: bool = False,
    ) -> None:
        """Runs the soffice command to convert a file.

        Args:
            input_path: The path to the input file.
            output_dir: The path to the output directory.
            is_spreadsheet: Whether the file is a spreadsheet.
        """
        if is_spreadsheet:
            filter_options = {"AllSheets": True, "ScaleToPagesX": 1, "ScaleToPagesY": 1}
            target = f"pdf:calc_pdf_Export:{json.dumps(filter_options)}"
        else:
            target = "pdf:writer_pdf_Export"

        user_profile = output_dir / "lo-profile"
        user_profile.mkdir(exist_ok=True, parents=True)

        cmd = [
            "soffice",
            "--headless",
            "--norestore",
            "--nodefault",
            "--nolockcheck",
            "--invisible",
            f"-env:UserInstallation=file://{user_profile}",
            "--convert-to",
            target,
            "--outdir",
            str(output_dir),
            str(input_path),
        ]
        self.logger.info(f"Running command: {' '.join(cmd)}")
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # nosec B603
        if completed.returncode != 0:
            self.logger.error(f"LibreOffice failed: {completed.stderr[:500]}")
            raise RuntimeError(f"LibreOffice failed: {completed.stderr[:500]}")
        self.logger.info(f"LibreOffice output: {completed.stdout[:500]}")
