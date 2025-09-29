"""
Shared fixtures for worker unit tests.
"""
import json
from unittest.mock import MagicMock

import pytest
from public_detective.worker.subscription import Subscription


@pytest.fixture
def mock_message() -> MagicMock:
    """Fixture for a mocked Pub/Sub message."""
    message_data = {"analysis_id": "123e4567-e89b-12d3-a456-426614174000"}
    message = MagicMock()
    message.data = json.dumps(message_data).encode("utf-8")
    message.message_id = "test-message-id"
    return message


@pytest.fixture
def mock_analysis_service() -> MagicMock:
    """Fixture for a mocked AnalysisService."""
    service = MagicMock()
    service.analysis_repo = MagicMock()
    return service


@pytest.fixture
def subscription(mock_analysis_service: MagicMock) -> Subscription:
    """Fixture to create a Subscription instance with mocked services."""
    sub = Subscription(analysis_service=mock_analysis_service)
    sub.pubsub_provider = MagicMock()
    sub.logger = MagicMock()
    return sub