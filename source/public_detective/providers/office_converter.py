import subprocess
import tempfile
from pathlib import Path
from threading import Lock

from public_detective.providers.logging import Logger, LoggingProvider


class OfficeConverterProvider:
    """A provider for converting office files using LibreOffice."""

    def __init__(self) -> None:
        """Initializes the provider."""
        self.logger: Logger = LoggingProvider().get_logger()
        self._lock = Lock()

    def to_pdf(self, file_content: bytes, original_extension: str) -> bytes:
        """Converts an office file to PDF.

        Args:
            file_content: The content of the file to convert.
            original_extension: The original extension of the file.

        Returns:
            The content of the converted PDF file.
        """
        with self._lock:
            with tempfile.TemporaryDirectory() as td:
                tmp_dir = Path(td)
                in_path = tmp_dir / f"input{original_extension}"
                in_path.write_bytes(file_content)

                self._run_soffice(in_path, tmp_dir)

                produced_files = list(tmp_dir.glob("*.pdf"))
                if not produced_files:
                    raise RuntimeError("LibreOffice conversion failed to produce a PDF file.")

                out_file = produced_files[0]
                return out_file.read_bytes()

    def _run_soffice(self, input_path: Path, output_dir: Path, target: str = "pdf:writer_pdf_Export"):
        """Runs the soffice command to convert a file.

        Args:
            input_path: The path to the input file.
            output_dir: The path to the output directory.
            target: The target format for the conversion.
        """
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
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if completed.returncode != 0:
            self.logger.error(f"LibreOffice failed: {completed.stderr[:500]}")
            raise RuntimeError(f"LibreOffice failed: {completed.stderr[:500]}")
        self.logger.info(f"LibreOffice output: {completed.stdout[:500]}")
