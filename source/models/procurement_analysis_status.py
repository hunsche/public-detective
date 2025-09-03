"""This module defines the enumeration for procurement analysis statuses."""

from enum import StrEnum


class ProcurementAnalysisStatus(StrEnum):
    """Represents the possible lifecycle statuses of a procurement analysis."""

    PENDING_ANALYSIS = "PENDING_ANALYSIS"
    """The analysis has been created but is waiting to be processed."""

    ANALYSIS_IN_PROGRESS = "ANALYSIS_IN_PROGRESS"
    """The analysis is actively being processed by a worker."""

    ANALYSIS_SUCCESSFUL = "ANALYSIS_SUCCESSFUL"
    """The analysis was completed without any unrecoverable errors."""

    ANALYSIS_FAILED = "ANALYSIS_FAILED"
    """The analysis could not be completed due to a critical error."""

    TIMEOUT = "TIMEOUT"
    """The analysis was marked as timed out after running for too long."""
