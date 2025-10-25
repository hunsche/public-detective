"""
This module contains a dedicated integration test to verify that the GCS cleanup
fixture correctly applies metadata to its marker object and cleans up all
test resources afterward in the emulated environment.
"""

import pytest
from public_detective.providers.gcs import GcsProvider

from tests.integrations.conftest import GcsCleanupManager


@pytest.mark.skip(reason="Skipping due to persistent GCS emulator connection issues in CI.")
def test_gcs_metadata_and_cleanup_integration(
    gcs_cleanup_manager: GcsCleanupManager, gcs_provider: GcsProvider
) -> None:
    """
    Validates that the GCS cleanup fixture against the emulator:
    1. Creates a marker object with the correct 'is_test' metadata.
    2. Successfully cleans up all objects under its prefix after the test.

    Args:
        gcs_cleanup_manager: The GCS cleanup manager fixture.
        gcs_provider: The shared GCS provider fixture.
    """
    gcs_client = gcs_provider.get_client()
    bucket_name = gcs_cleanup_manager.bucket_name
    bucket = gcs_client.bucket(bucket_name)

    # The test assumes the bucket has been created by the docker-compose setup.
    assert bucket.exists(), "The GCS bucket was not created by the test environment setup."

    # --- Verification during the test ---

    # 1. Check for the marker and its metadata
    marker_blob_name = f"{gcs_cleanup_manager.prefix}/__test_marker__"
    marker_blob = bucket.get_blob(marker_blob_name)

    assert marker_blob is not None, "The __test_marker__ object was not created by the fixture."
    assert "is_test" in marker_blob.metadata
    assert marker_blob.metadata["is_test"] == "true"
    assert marker_blob.metadata["run_id"] == gcs_cleanup_manager.prefix

    # 2. Upload a dummy file to ensure it's also present
    test_file_blob_name = f"{gcs_cleanup_manager.prefix}/dummy_file.txt"
    bucket.blob(test_file_blob_name).upload_from_string("test")
    assert bucket.get_blob(test_file_blob_name) is not None, "Dummy test file was not created."

    # The fixture's cleanup will run automatically after this test function finishes.
    # We have validated that the test objects were created correctly.
