import uuid
from collections.abc import Generator
from datetime import datetime, timezone

import pytest
from _pytest.nodes import Item
from google.api_core import exceptions
from google.cloud.storage import Client
from public_detective.providers.config import ConfigProvider
from public_detective.providers.gcs import GcsProvider
from pydantic import BaseModel, ConfigDict, model_validator


def pytest_collection_modifyitems(items: list[Item]) -> None:
    """Dynamically adds markers to tests based on their file path.

    Args:
        items: A list of test items collected by pytest.
    """
    for item in items:
        if "units" in item.path.parts:
            item.add_marker(pytest.mark.unit)
        elif "integrations" in item.path.parts:
            item.add_marker(pytest.mark.integration)
        elif "e2e" in item.path.parts:
            item.add_marker(pytest.mark.e2e)


class GcsCleanupManager(BaseModel):
    """Manages the lifecycle of a temporary GCS folder for a test."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    prefix: str
    bucket_name: str
    gcs_provider: GcsProvider

    @model_validator(mode="after")
    def _create_test_marker_on_init(self) -> "GcsCleanupManager":
        """Creates a marker to identify the test folder after initialization."""
        self._create_test_marker()
        return self

    def _create_test_marker(self) -> None:
        """Creates a sentinel object with metadata to mark the folder as a test resource."""
        marker_blob_name = f"{self.prefix}/__test_marker__"
        self.gcs_provider.upload_file(
            bucket_name=self.bucket_name,
            destination_blob_name=marker_blob_name,
            content=b"",
            content_type="text/plain",
            metadata={
                "is_test": "true",
                "created_at": datetime.now(timezone.utc).isoformat(),
                "run_id": self.prefix,
            },
        )

    def cleanup(self) -> None:
        """Deletes all objects under the prefix, including the marker."""
        # Create a brand new, fresh client to avoid any caching issues and
        # ensure we get the latest state of the bucket.
        config = ConfigProvider.get_config()
        gcs_client = Client(project=config.GCP_PROJECT)
        bucket = gcs_client.bucket(self.bucket_name)

        try:
            blobs_to_delete = list(bucket.list_blobs(prefix=self.prefix))
            print(f"--- Found {len(blobs_to_delete)} blobs to clean up for prefix {self.prefix} ---")
            for blob in blobs_to_delete:
                try:
                    blob.delete()
                except exceptions.NotFound:
                    pass  # Object might have been deleted by another process
            print(f"--- Cleanup successful for prefix {self.prefix} ---")
        except exceptions.NotFound:
            pass  # Bucket or prefix might already be gone


@pytest.fixture(scope="function")
def gcs_cleanup_manager(
    request: pytest.FixtureRequest, gcs_provider: GcsProvider
) -> Generator[GcsCleanupManager, None, None]:
    """A fixture to manage GCS cleanup for tests.

    It creates a unique prefix for the test, marks it with a sentinel file,
    and cleans up everything under that prefix after the test runs.

    Args:
        request: The pytest request object.
        gcs_provider: A fixture that provides a configured GCS provider.

    Yields:
        An instance of the GcsCleanupManager.
    """
    config = ConfigProvider.get_config()
    bucket_name = config.GCP_GCS_BUCKET_PROCUREMENTS

    # Default prefix for integration tests
    prefix_base = "integration-test"
    # Check if the test is in the 'e2e' directory and update prefix
    if "e2e" in request.path.parts:
        prefix_base = "e2e-test"

    unique_id = uuid.uuid4().hex[:8]
    prefix = f"{prefix_base}-{unique_id}"

    manager = GcsCleanupManager(prefix=prefix, bucket_name=bucket_name, gcs_provider=gcs_provider)
    yield manager
    manager.cleanup()
