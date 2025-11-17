"""This module defines the enumeration for procurement analysis statuses."""

from enum import StrEnum, auto


class ProcurementAnalysisStatus(StrEnum):
    """Represents the possible lifecycle statuses of a procurement analysis."""

    @staticmethod
    def _generate_next_value_(
        name: str,
        _start: int,
        _count: int,
        _last_values: list[str],
    ) -> str:
        """Returns the uppercase member name to keep values stable.

        Args:
            name: The enum member name being assigned.
            _start: The first automatic value (unused).
            _count: Number of existing members (unused).
            _last_values: Previously assigned values (unused).

        Returns:
            The uppercase member name, preserving the legacy stored values.
        """
        return name

    PENDING_TOKEN_CALCULATION = auto()
    """The analysis record has been created, but is awaiting token calculation."""
    PENDING_ANALYSIS = auto()
    """The analysis has been created but is waiting to be processed."""

    ANALYSIS_IN_PROGRESS = auto()
    """The analysis is actively being processed by a worker."""

    ANALYSIS_SUCCESSFUL = auto()
    """The analysis was completed without any unrecoverable errors."""

    ANALYSIS_FAILED = auto()
    """The analysis could not be completed due to a critical error."""
