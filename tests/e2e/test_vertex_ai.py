import os
import time
import uuid
from pathlib import Path

import pytest
import vertexai
from google.cloud import storage
from vertexai.generative_models import GenerativeModel, Part


@pytest.fixture(scope="module")
def e2e_vertex_setup():
    """Set up the environment for Vertex AI E2E tests."""
    os.environ.pop("GCP_GCS_HOST", None)
    os.environ.pop("GCP_AI_HOST", None)

    project_id = "total-entity-463718-k1"
    os.environ["GCP_PROJECT"] = project_id

    credentials_path = os.path.expanduser("~/.gcp/credentials.json")
    if not os.path.exists(credentials_path):
        pytest.fail(f"Service account credentials not found at {credentials_path}")

    # Set the file path for standard ADC used by libraries directly
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = credentials_path

    yield

    os.environ.pop("GCP_PROJECT", None)
    os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)


@pytest.fixture(scope="module")
def gcs_client(e2e_vertex_setup):
    """Initializes the GCS client using Application Default Credentials."""
    return storage.Client()


@pytest.fixture(scope="module")
def test_bucket(gcs_client):
    """Ensures the hardcoded test bucket exists and provides it."""
    bucket_name = "vertex-ai-test-files"
    bucket = gcs_client.bucket(bucket_name)
    if not bucket.exists():
        pytest.fail(f"The required GCS bucket '{bucket_name}' does not exist.")
    return bucket


@pytest.fixture(scope="module")
def vertex_ai_model(e2e_vertex_setup):
    """Initializes the Vertex AI Generative Model using ADC."""
    vertexai.init()
    return GenerativeModel("gemini-2.5-pro")


@pytest.mark.timeout(60)
def test_simple_vertex_ai_analysis(vertex_ai_model, test_bucket, tmp_path: Path):
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

    try:
        response = vertex_ai_model.generate_content([prompt, file_part])
        # 4. Assert the response
        assert response, "Received an empty response from Vertex AI."
        assert "banana" in response.text.lower(), f"Expected 'banana' in response, but got: {response.text}"
    finally:
        # 5. Teardown: Ensure blob is deleted even if assertion fails
        if blob.exists():
            blob.delete()
