"""A flake8 plugin to forbid hash comments."""

import ast
from typing import Any, Generator


class NoHashCommentsPlugin:
    """A flake8 plugin to forbid hash comments."""

    name = "flake8-no-hash-comments"
    version = "0.1.0"

    # Define the error code and message.
    NOHASH_ERROR_CODE = "NHC001"
    NOHASH_ERROR_MESSAGE = f"{NOHASH_ERROR_CODE} hash comments are not allowed"

    # A class attribute to store the options.
    _lines: list[str] = []

    def __init__(self, tree: ast.AST, filename: str, lines: list[str]):
        """The constructor, called by flake8.

        Args:
            tree: The AST tree of the file.
            filename: The name of the file being processed.
            lines: The lines of the file.
        """
        self._tree = tree
        self._filename = filename
        self._lines = lines

    @classmethod
    def add_options(cls, parser: Any) -> None:
        """A hook to add new options to the flake8 parser.

        Args:
            parser: The flake8 option parser.
        """
        # This method is called by flake8 to add new options.
        # We don't need any options for this plugin.

    @classmethod
    def parse_options(cls, options: Any) -> None:
        """A hook to parse the options.

        Args:
            options: The options parsed by flake8.
        """
        # This method is called by flake8 to parse the options.
        # We don't need any options for this plugin.

    def run(self) -> Generator[tuple[int, int, str, type[Any]], None, None]:
        """The main method, called by flake8.

        Yields:
            A tuple containing the line number, column, error message, and plugin type.
        """
        for i, line in enumerate(self._lines):
            line_number = i + 1
            # We're looking for comments that start with a hash.
            # We need to be careful not to flag shebangs or encoding declarations.
            stripped_line = line.strip()
            if stripped_line.startswith("#"):
                if stripped_line.startswith("#!") or "coding:" in stripped_line:
                    continue
                yield (
                    line_number,
                    line.find("#"),
                    self.NOHASH_ERROR_MESSAGE,
                    type(self),
                )