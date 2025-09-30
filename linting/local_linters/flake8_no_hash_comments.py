"""A flake8 plugin to disallow hash comments."""

from __future__ import annotations

import tokenize
from collections.abc import Iterable

Err = tuple[int, int, str, type["NoHashCommentsPlugin"]]


class NoHashCommentsPlugin:
    """A flake8 plugin to disallow hash comments."""

    name = "flake8-no-hash-comments"
    version = "0.1.5"

    allowed_prefixes: tuple[str, ...] = ("#!",)
    allowlist_substrings: tuple[str, ...] = ()

    code = "NHC9001"
    msg = (
        f"{code} Hash comments are not allowed; code should be self-explanatory "
        "and docstrings should document behavior and intent"
    )

    def __init__(self, _tree, filename: str, lines: list[str]):
        """Initialize the plugin.

        Args:
            _tree: The abstract syntax tree (unused).
            filename: The name of the file being linted.
            lines: The lines of the file.
        """
        self.filename = filename
        self.lines = lines

    @classmethod
    def add_options(cls, parser) -> None:
        """Add options to the flake8 parser.

        Args:
            parser: The options parser.
        """
        parser.add_option(
            "--no-hash-allow-prefixes",
            default="#!",
            parse_from_config=True,
            help="Allowed prefixes for the first line. Default: '#!'. Comma separated.",
        )
        parser.add_option(
            "--no-hash-allow-substrings",
            default="",
            parse_from_config=True,
            help="Allowed substrings inside comments. Comma separated.",
        )

    @classmethod
    def parse_options(cls, options) -> None:
        """Parse the options.

        Args:
            options: The options to parse.
        """

        def split_csv(csv_string: str) -> tuple[str, ...]:
            return tuple(item.strip() for item in csv_string.split(",") if item.strip())

        cls.allowed_prefixes = split_csv(options.no_hash_allow_prefixes or "")
        cls.allowlist_substrings = split_csv(options.no_hash_allow_substrings or "")

    def run(self) -> Iterable[Err]:
        """Run the linter.

        Yields:
            An error for each hash comment found.
        """
        try:
            reader = tokenize.generate_tokens(iter(self.lines).__next__)

            first_line = True
            for tok_type, tok_str, (lineno, _col), _, _ in reader:
                if tok_type != tokenize.COMMENT:
                    if tok_type in (tokenize.NL, tokenize.NEWLINE):
                        first_line = False
                    continue

                text = tok_str or ""

                if "noqa" in text:
                    continue
                if first_line and any(text.startswith(p) for p in self.allowed_prefixes):
                    continue
                if self.allowlist_substrings and any(substring in text for substring in self.allowlist_substrings):
                    continue

                yield (lineno, 0, self.msg, type(self))

        except tokenize.TokenError:
            return
