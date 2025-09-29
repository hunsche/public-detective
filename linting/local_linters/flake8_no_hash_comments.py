"""A flake8 plugin to disallow hash comments."""

from __future__ import annotations

import tokenize
from collections.abc import Iterable
from typing import Any

Err = tuple[int, int, str, type["NoHashCommentsPlugin"]]


class NoHashCommentsPlugin:
    """A flake8 plugin that disallows hash comments in Python code."""

    name = "flake8-no-hash-comments"
    version = "0.1.5"

    allowed_prefixes: tuple[str, ...] = ("#!",)
    allowlist_substrings: tuple[str, ...] = ()

    code = "NHC9001"
    msg = (
        f"{code} Hash comments are not allowed; code should be self-explanatory "
        "and docstrings should document behavior and intent"
    )

    def __init__(self, filename: str, lines: list[str]) -> None:
        """Initialize the plugin with the file details.

        Args:
            filename: The name of the file being processed.
            lines: The lines of the file.
        """
        self.filename = filename
        self.lines = lines

    @classmethod
    def add_options(cls, parser: Any) -> None:
        """Add command-line options for the plugin.

        Args:
            parser: The flake8 option parser.
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
    def parse_options(cls, options: Any) -> None:
        """Parse the command-line options.

        Args:
            options: The parsed options.
        """

        def split_csv(csv_string: str) -> tuple[str, ...]:
            return tuple(x.strip() for x in csv_string.split(",") if x.strip())

        cls.allowed_prefixes = split_csv(options.no_hash_allow_prefixes or "")
        cls.allowlist_substrings = split_csv(options.no_hash_allow_substrings or "")

    def run(self) -> Iterable[Err]:
        """Run the linter on the file and yield any errors found.

        Yields:
            A tuple for each error found.
        """
        try:
            reader = tokenize.generate_tokens(iter(self.lines).__next__)

            first_line = True
            for tok_type, tok_str, (lineno, _), _, _ in reader:
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
