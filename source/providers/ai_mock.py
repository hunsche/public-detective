"""
This module provides a mock implementation of the AiProvider for testing purposes.
"""

from models.analysis import Analysis, AnalysisResult
from providers.gcs import GcsFile


class MockAiProvider:
    """A mock implementation of the AiProvider that returns canned responses
    without making actual API calls."""

    def count_tokens_for_analysis(self, prompt: str, files_for_ai: list[GcsFile]) -> int:
        """Returns a fixed token count for any given input."""
        return 1500  # Return a static, realistic token count

    def run_analysis(self, prompt: str, files_for_ai: list[GcsFile], correlation_id: str) -> AnalysisResult:
        """Returns a static, pre-defined analysis result."""
        return AnalysisResult(
            procurement_control_number=f"mock-pcn-{correlation_id}",
            ai_analysis=Analysis(
                risk_score=7,
                risk_score_rationale="This is a mocked rationale for the risk score.",
                summary="This is a mocked summary of the procurement analysis.",
                red_flags=[],
            ),
            warnings=["This is a mock warning."],
            document_hash="mock-document-hash",
        )
