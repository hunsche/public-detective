"""This module provides a factory for creating and configuring progress bars."""

from collections.abc import Sized
from contextlib import contextmanager
from typing import Generator, TypeVar

import click

T = TypeVar("T")


class ProgressFactory:
    """A factory for creating and configuring progress bars."""

    def make(self, iterable: Sized, label: str) -> click.progressbar:
        """Creates a new progress bar.

        Args:
            iterable: The iterable to track.
            label: The label for the progress bar.

        Returns:
            A configured progress bar.
        """
        return click.progressbar(
            iterable,
            label=label,
            bar_template="%(label)s [%(bar)s] %(info)s",
            show_pos=True,
            show_percent=True,
        )


@contextmanager
def null_progress(iterable: Sized, label: str) -> Generator[Sized, None, None]:  # noqa: F841
    """A null progress bar that does nothing.

    Args:
        iterable: The iterable to track.
        label: The label for the progress bar.

    Yields:
        The original iterable.
    """
    yield iterable
