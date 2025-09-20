from public_detective.providers.ai import AiProvider
from pydantic import BaseModel
from sqlalchemy.engine import Engine


class MockOutputSchema(BaseModel):
    summary: str


def test_token_counting(db_session: Engine) -> None:
    """
    Tests the token counting functionality against the live Vertex AI API.
    """
    ai_provider = AiProvider(output_schema=MockOutputSchema)
    prompt = "This is a test prompt."
    files = [("test.txt", b"This is a test file.")]

    input_tokens, output_tokens, thinking_tokens = ai_provider.count_tokens_for_analysis(prompt, files)

    assert isinstance(input_tokens, int)
    assert input_tokens > 0
    assert isinstance(output_tokens, int)
    assert isinstance(thinking_tokens, int)
