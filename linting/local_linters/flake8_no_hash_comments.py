"""A flake8 plugin to forbid hash comments using the tokenize module correctly."""

import ast
import tokenize
from collections.abc import Generator
from typing import Any


class NoHashCommentsPlugin:
    """A flake8 plugin to forbid hash comments."""

    name = "flake8-no-hash-comments"
    version = "1.1.0"

    NOHASH_ERROR_CODE = "NHC9001"
    NOHASH_ERROR_MESSAGE = (
        f"{NOHASH_ERROR_CODE} Hash comments are not allowed; use docstrings or remove unnecessary comments"
    )

    allowed_prefixes: list[str] = []
    allowed_substrings: list[str] = []

    def __init__(self, tree: ast.AST, filename: str, lines: list[str]):
        """The constructor, called by flake8.

        Args:
            tree: The AST tree.
            filename: The name of the file.
            lines: The lines of the file. Kept for compatibility, but not used by run().
        """
        self._tree = tree
        self._filename = filename
        self._lines = lines
        self.prefixes_tuple = tuple(self.allowed_prefixes)
        self.substrings_tuple = tuple(self.allowed_substrings)

    @classmethod
    def add_options(cls, parser: Any) -> None:
        """A hook to add new options to the flake8 parser.

        Args:
            parser: The flake8 option parser.
        """
        parser.add_option(
            "--no-hash-allow-prefixes",
            comma_separated_list=True,
            parse_from_config=True,
            default=[],
            help="A comma-separated list of prefixes to allow for hash comments.",
        )
        parser.add_option(
            "--no-hash-allow-substrings",
            comma_separated_list=True,
            parse_from_config=True,
            default=[],
            help="A comma-separated list of substrings to allow for hash comments.",
        )

    @classmethod
    def parse_options(cls, options: Any) -> None:
        """A hook to parse the options.

        Args:
            options: The options parsed by flake8.
        """
        cls.allowed_prefixes = options.no_hash_allow_prefixes or []
        cls.allowed_substrings = options.no_hash_allow_substrings or []

    def _is_allowed_comment(self, comment: str) -> bool:
        """Check if a comment is allowed by the configured rules.

        Args:
            comment: The comment string.

        Returns:
            True if the comment is allowed, False otherwise.
        """
        is_coding_directive = "coding:" in comment
        if is_coding_directive:
            return True
        stripped_comment = comment.lstrip("# ")
        if any(stripped_comment.startswith(p) for p in self.prefixes_tuple):
            return True
        if any(s in comment for s in self.substrings_tuple):
            return True
        return False

    def run(self) -> Generator[tuple[int, int, str, type[Any]], None, None]:
        """The main method, called by flake8.

        It opens the file using `tokenize.open` for automatic encoding detection,
        then iterates through tokens to find and validate comments.
        It ignores files that are not valid Python, have been deleted, or have
        other OS or syntax errors by catching the relevant exceptions.

        Yields:
            A tuple of (line number, column, message, type).
        """
        if self._filename in ("stdin", None):
            return

        try:
            with tokenize.open(self._filename) as f:
                tokens = tokenize.generate_tokens(f.readline)
                for token in tokens:
                    if token.type == tokenize.COMMENT and not token.string.startswith("#!"):
                        if not self._is_allowed_comment(token.string):
                            yield (
                                token.start[0],
                                token.start[1],
                                self.NOHASH_ERROR_MESSAGE,
                                type(self),
                            )
        except (tokenize.TokenError, SyntaxError, OSError):
            pass
