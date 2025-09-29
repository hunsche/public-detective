"This module contains E2E tests for token counting."

import uuid
from collections.abc import Callable
from pathlib import Path

from public_detective.providers.ai import AiProvider
from public_detective.providers.config import Config, ConfigProvider
from public_detective.providers.gcs import GcsProvider
from pydantic import BaseModel
from sqlalchemy.engine import Engine


class MockOutputSchema(BaseModel):
    """A mock output schema for testing."""

    summary: str


def test_token_counting_with_gcs_file(
    db_session: Engine,  # noqa: F841
    tmp_path: Path,
    gcs_cleanup_manager: Callable[[str], None],
) -> None:
    """
    Tests the token counting functionality for a prompt and a GCS file.

    Args:
        db_session: The SQLAlchemy engine instance.
        tmp_path: The temporary path fixture from pytest.
        gcs_cleanup_manager: The GCS cleanup fixture.
    """
    # 1. Setup providers and config
    ai_provider = AiProvider(output_schema=MockOutputSchema)
    gcs_provider = GcsProvider()
    config: Config = ConfigProvider.get_config()
    bucket_name = config.GCP_GCS_BUCKET_PROCUREMENTS

    # 2. Create and upload a temporary file
    local_file = tmp_path / "test.txt"
    local_file.write_text("This is a test file with some content.")
    blob_name = f"test_token_counting/{uuid.uuid4().hex}.txt"
    gcs_cleanup_manager(blob_name)

    gcs_provider.upload_file(
        bucket_name=bucket_name,
        destination_blob_name=blob_name,
        content=local_file.read_bytes(),
        content_type="text/plain",
    )

    # 3. Construct the GCS URI and prompt
    gcs_uri = f"gs://{bucket_name}/{blob_name}"
    prompt = "This is a test prompt."
    files = [gcs_uri]

    # 4. Call the token counting method
    input_tokens, output_tokens, thinking_tokens = ai_provider.count_tokens_for_analysis(prompt, files)

    # 5. Assert the results
    assert isinstance(input_tokens, int)
    assert input_tokens > 0, "Input tokens should be greater than zero."
    assert isinstance(output_tokens, int)
    assert isinstance(thinking_tokens, int)
