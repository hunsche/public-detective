import os
import pytest
from providers.ai import AiProvider
from pydantic import BaseModel


class MockOutputSchema(BaseModel):
    summary: str


@pytest.fixture(scope="module")
def e2e_token_counting_setup():
    """Sets up the environment variables for the token counting E2E test."""
    # Ensure E2E tests run against real GCP services, not an emulator.
    os.environ.pop("GCP_AI_HOST", None)

    os.environ["GCP_PROJECT"] = "total-entity-463718-k1"
    credentials_path = os.path.expanduser("~/.gcp/credentials.json")
    if not os.path.exists(credentials_path):
        pytest.fail(f"Service account credentials not found at {credentials_path}")

    with open(credentials_path, "r") as f:
        gcs_credentials_json = f.read()
    os.environ["GCP_SERVICE_ACCOUNT_CREDENTIALS"] = gcs_credentials_json

    yield

    os.environ.pop("GCP_PROJECT", None)
    os.environ.pop("GCP_SERVICE_ACCOUNT_CREDENTIALS", None)


def test_token_counting(e2e_token_counting_setup):
    """
    Tests the token counting functionality against the live Vertex AI API.
    """
    ai_provider = AiProvider(output_schema=MockOutputSchema)
    prompt = "This is a test prompt."
    files = [("test.txt", b"This is a test file.")]

    token_count, _ = ai_provider.count_tokens_for_analysis(prompt, files)

    assert isinstance(token_count, int)
    assert token_count > 0
