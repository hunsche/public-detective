"""This module provides a mock implementation of the AiProvider for testing.

It allows for the simulation of AI interactions without making actual API
calls, which is essential for rapid, isolated, and cost-effective testing of
services that depend on the AiProvider.
"""

from typing import Generic, TypeVar

from models.analyses import Analysis
from pydantic import BaseModel

PydanticModel = TypeVar("PydanticModel", bound=BaseModel)


class MockAiProvider(Generic[PydanticModel]):
    """A mock AiProvider that returns canned responses without API calls."""

    output_schema: type[PydanticModel]

    def __init__(self, output_schema: type[PydanticModel]):
        """
        Initializes the MockAiProvider with a specific output schema.

        Args:
            output_schema: The Pydantic model class that this provider instance
                           will use for all structured outputs.
        """
        self.output_schema = output_schema

    def get_structured_analysis(
        self, prompt: str, files: list[tuple[str, bytes]], max_output_tokens: int | None = None
    ) -> tuple[PydanticModel, int, int]:
        """Returns a static, pre-defined analysis result and token counts.

        If the requested output_schema is the 'Analysis' model, it returns a
        detailed, hardcoded mock. Otherwise, it returns a default-constructed
        instance of the requested schema.

        Args:
            prompt: The instructional prompt for the AI model (ignored).
            files: A list of file tuples (ignored).
            max_output_tokens: An optional token limit (ignored).

        Returns:
            A tuple containing a mock Pydantic model instance, and static
            input and output token counts.
        """
        if self.output_schema == Analysis:
            # If the schema is 'Analysis', return the detailed, hardcoded mock.
            mock_analysis = Analysis(
                risk_score=7,
                risk_score_rationale="This is a mocked rationale.",
                procurement_summary="This is a mocked procurement summary.",
                analysis_summary="This is a mocked analysis summary.",
                red_flags=[],
                seo_keywords=["mock", "test", "analysis"],
            )
            # We need to cast here to satisfy the type checker, as it doesn't
            # know that self.output_schema being Analysis means PydanticModel is Analysis.
            return mock_analysis, 1000, 200  # type: ignore

        # For any other schema, return a default-constructed model.
        # model_construct() creates an instance without validation, which is
        # perfect for mocking.
        return self.output_schema.model_construct(), 50, 50

    def count_tokens_for_analysis(self, prompt: str, files: list[tuple[str, bytes]]) -> tuple[int, int]:
        """Returns a fixed token count for any given input.

        Args:
            prompt: The instructional prompt (ignored).
            files: A list of file tuples (ignored).

        Returns:
            A tuple with a static input token count and zero for output tokens.
        """
        return 1500, 0
