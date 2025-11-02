"""Providers for converting image files with ImageMagick."""

import subprocess  # nosec B404
import tempfile
from pathlib import Path

from public_detective.providers.logging import Logger, LoggingProvider


class ImageConverterProvider:
    """A provider for converting image files using ImageMagick."""

    logger: Logger

    def __init__(self) -> None:
        """Initializes the provider."""
        self.logger = LoggingProvider().get_logger()

    def to_png(self, file_content: bytes, original_extension: str) -> bytes:
        """Converts an image file to PNG.

        Args:
            file_content: The content of the file to convert.
            original_extension: The original extension of the file.

        Returns:
            The content of the converted PNG file.
        """
        with tempfile.TemporaryDirectory() as td:
            tmp_dir = Path(td)
            in_path = tmp_dir / f"input{original_extension}"
            in_path.write_bytes(file_content)
            out_path = tmp_dir / "output.png"

            self._run_convert(in_path, out_path)

            if not out_path.exists():
                raise RuntimeError("ImageMagick conversion failed to produce a PNG file.")

            return out_path.read_bytes()

    def _run_convert(
        self,
        input_path: Path,
        output_path: Path,
    ) -> None:
        """Runs the convert command to convert a file.

        Args:
            input_path: The path to the input file.
            output_path: The path to the output file.
        """
        cmd = [
            "convert",
            str(input_path),
            str(output_path),
        ]
        self.logger.info(f"Running command: {' '.join(cmd)}")
        completed = subprocess.run(cmd, capture_output=True, text=True, timeout=120)  # nosec B603
        if completed.returncode != 0:
            self.logger.error(f"ImageMagick failed: {completed.stderr[:500]}")
            raise RuntimeError(f"ImageMagick failed: {completed.stderr[:500]}")
        self.logger.info(f"ImageMagick output: {completed.stdout[:500]}")
