"""This module contains shared fixtures for all unit tests."""

import os

import pytest


@pytest.fixture(scope="session", autouse=True)
def unset_gcp_credentials() -> None:
    """Unsets GCP-related environment variables for the entire test session.

    This fixture ensures that unit tests run in a completely isolated
    environment, preventing any accidental calls to real GCP services by

    guaranteeing that no credentials or specific resource names are available.
    """
    os.environ.pop("GCP_SERVICE_ACCOUNT_CREDENTIALS", None)
    os.environ.pop("GCP_GCS_BUCKET_PROCUREMENTS", None)
