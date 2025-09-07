import os
import pytest
from providers.ai import AiProvider
from pydantic import BaseModel


class MockOutputSchema(BaseModel):
    summary: str


def test_token_counting(e2e_environment: None) -> None:
    """
    Tests the token counting functionality against the live Vertex AI API.
    """
    ai_provider = AiProvider(output_schema=MockOutputSchema)
    prompt = "This is a test prompt."
    files = [("test.txt", b"This is a test file.")]

    token_count, _ = ai_provider.count_tokens_for_analysis(prompt, files)

    assert isinstance(token_count, int)
    assert token_count > 0
