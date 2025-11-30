"""
This module contains a dedicated E2E test to verify that the GCS cleanup
fixture correctly creates and removes test resources in the REAL GCS bucket
by running a real CLI command.
"""

from typing import Any

import pytest
from public_detective.providers.gcs import GcsProvider
from sqlalchemy import text
from sqlalchemy.engine import Engine

from tests.e2e.workflows.conftest import GcsCleanupManager, run_command


@pytest.mark.e2e
def test_gcs_cleanup_e2e(
    db_session: Engine,
    e2e_pubsub: tuple[Any, Any],
    gcs_cleanup_manager: GcsCleanupManager,
    gcs_provider: GcsProvider,
) -> None:
    """
    Validates that the GCS cleanup fixture works with a real CLI command.

    This test works by:
    1.  Running the `analysis prepare` command to generate real artifacts in GCS
        under a unique, test-specific prefix.
    2.  Asserting that the artifacts were successfully created.
    3.  Relying on the `gcs_cleanup_manager` fixture's teardown process to
        automatically delete all the artifacts created during the test. The
        fixture itself handles the verification of the cleanup.

    Args:
        db_session: The SQLAlchemy engine instance.
        e2e_pubsub: The Pub/Sub client and topic name.
        gcs_cleanup_manager: The GCS cleanup manager fixture.
        gcs_provider: The GCS provider instance.
    """
    # The e2e_pubsub fixture is required to set up the Pub/Sub environment for
    # the CLI commands, even if it's not directly used in the test function.
    assert e2e_pubsub is not None

    # The gcs_cleanup_manager fixture has already created a unique prefix and
    # a marker file in GCS. Now, we run a real CLI command to generate more
    # artifacts in that same prefixed path.
    gcs_prefix = gcs_cleanup_manager.prefix
    prepare_command = (
        f"poetry run pd analysis --gcs-path-prefix {gcs_prefix} prepare "
        f"--start-date 2025-08-23 --end-date 2025-08-23 --max-messages 1"
    )
    run_command(prepare_command)

    with db_session.connect() as connection:
        result = connection.execute(text("SELECT analysis_id FROM procurement_analyses LIMIT 1")).scalar_one()
        analysis_id = result

    run_command(f"poetry run pd analysis run --analysis-id {analysis_id}")
    run_command(f"poetry run pd worker start --max-messages 1 --timeout 15 " f"--gcs-path-prefix {gcs_prefix}")

    # Verify that the CLI command actually created files in the bucket.
    # The marker file is created by the fixture, so we expect more than 1 file.
    blobs = gcs_provider.list_blobs(gcs_cleanup_manager.bucket_name, gcs_prefix)
    assert len(blobs) > 1, f"Expected artifacts to be created in GCS under prefix '{gcs_prefix}', but found none."

    print(
        f"\n--- Verified {len(blobs)} test objects created in gs://{gcs_cleanup_manager.bucket_name}/{gcs_prefix}/ ---"
    )
    # The fixture's cleanup will run automatically after this test function
    # finishes, deleting all the blobs we just verified.
