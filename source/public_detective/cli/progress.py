"""This module provides a factory for creating progress bars."""

from collections.abc import Iterable, Iterator
from contextlib import AbstractContextManager, contextmanager

import click


class ProgressFactory:
    """Creates a progress bar using click.progressbar."""

    def make(self, iterable: Iterable, label: str) -> AbstractContextManager[Iterable]:
        """Creates a new progress bar.

        Args:
            iterable: The iterable to track.
            label: The label to display for the progress bar.

        Returns:
            A click.progressbar instance.
        """
        return click.progressbar(iterable, label=label)


@contextmanager
def null_progress(iterable: Iterable, label: str) -> Iterator[Iterable]:
    """A null progress bar that does nothing but yield the iterable.

    Args:
        iterable: The iterable to yield.
        label: The label (ignored).

    Yields:
        The original iterable.
    """
    # The label is ignored, but kept for interface compatibility.
    del label
    yield iterable
