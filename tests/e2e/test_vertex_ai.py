import os
import time
import uuid
from pathlib import Path

import pytest
import vertexai
from google.cloud.storage import Bucket, Client
from vertexai.generative_models import GenerativeModel, Part


@pytest.fixture(scope="function")
def gcs_client(e2e_environment: None) -> Client:
    """Initializes the GCS client using Application Default Credentials."""
    return Client()


@pytest.fixture(scope="function")
def test_bucket(gcs_client: Client) -> Bucket:
    """Ensures the hardcoded test bucket exists and provides it."""
    bucket_name = os.environ["GCP_VERTEX_AI_BUCKET"]
    bucket = gcs_client.bucket(bucket_name)
    assert bucket.exists(), f"The required GCS bucket '{bucket_name}' does not exist."
    return bucket


@pytest.fixture(scope="function")
def vertex_ai_model(e2e_environment: None) -> GenerativeModel:
    """Initializes the Vertex AI Generative Model using ADC."""
    vertexai.init()
    return GenerativeModel("gemini-2.5-pro")


@pytest.mark.timeout(60)
def test_simple_vertex_ai_analysis(vertex_ai_model: GenerativeModel, test_bucket: Bucket, tmp_path: Path) -> None:
    """
    Performs a simple E2E test to verify Vertex AI and GCS connectivity.
    It uploads a simple text file and asks the model to read it.
    """
    # 1. Create a local test file
    local_file = tmp_path / "test.txt"
    local_file.write_text("The magic word is banana.")

    # 2. Upload to GCS
    blob_name = f"test-run-{uuid.uuid4().hex}/test.txt"
    blob = test_bucket.blob(blob_name)
    blob.upload_from_filename(str(local_file))

    # Add a small delay to ensure GCS object is fully available
    time.sleep(2)

    # 3. Call Vertex AI
    gcs_uri = f"gs://{test_bucket.name}/{blob_name}"
    file_part = Part.from_uri(uri=gcs_uri, mime_type="text/plain")
    prompt = "What is the magic word in the document?"
    contents: list[str | Part] = [prompt, file_part]

    try:
        response = vertex_ai_model.generate_content(contents)  # type: ignore[arg-type]
        # 4. Assert the response
        assert response, "Received an empty response from Vertex AI."
        assert "banana" in response.text.lower(), f"Expected 'banana' in response, but got: {response.text}"
    finally:
        # 5. Teardown: Ensure blob is deleted even if assertion fails
        if blob.exists():
            blob.delete()
