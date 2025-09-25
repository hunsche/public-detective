"""
Unit tests for the AnalysisService pre-analysis logic.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from public_detective.models.procurements import Procurement
from public_detective.services.analysis import AnalysisService


@pytest.fixture
def mock_dependencies() -> dict:
    """Fixture to create all mocked dependencies for AnalysisService.

    Returns:
        A dictionary of mocked dependencies.
    """
    return {
        "procurement_repo": MagicMock(),
        "analysis_repo": MagicMock(),
        "file_record_repo": MagicMock(),
        "status_history_repo": MagicMock(),
        "budget_ledger_repo": MagicMock(),
        "ai_provider": MagicMock(),
        "gcs_provider": MagicMock(),
        "pubsub_provider": MagicMock(),
    }


def test_run_pre_analysis_no_procurements_found(mock_dependencies: dict) -> None:
    """Tests that the pre-analysis job handles dates with no procurements.

    Args:
        mock_dependencies: The mocked dependencies.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = []
    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 1)

    # Act
    with patch.object(service, "_pre_analyze_procurement") as mock_pre_analyze:
        service.run_pre_analysis(start_date, end_date, batch_size=10, sleep_seconds=0)

    # Assert
    mock_pre_analyze.assert_not_called()
    assert service.procurement_repo.get_updated_procurements_with_raw_data.call_count == 1


def test_pre_analyze_procurement_idempotency(mock_dependencies: dict, mock_procurement: Procurement) -> None:
    """
    Tests that _pre_analyze_procurement skips processing if a procurement
    with the same hash already exists.

    Args:
        mock_dependencies: The mocked dependencies.
        mock_procurement: The mocked procurement.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    raw_data = {"key": "value"}
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    service.procurement_repo.get_procurement_by_hash.return_value = (
        mock_procurement  # Simulate finding an existing hash
    )

    service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)
    # Act
    service._pre_analyze_procurement(mock_procurement, raw_data)

    # Assert
    service.procurement_repo.get_latest_version.assert_not_called()
    service.procurement_repo.save_procurement_version.assert_not_called()


def test_pre_analyze_procurement_hash_exists_with_files(mock_dependencies: dict, mock_procurement: Procurement) -> None:
    """Test _pre_analyze_procurement when hash exists but files are processed."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    service.procurement_repo.get_procurement_by_hash.return_value = mock_procurement
    service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)

    service._pre_analyze_procurement(mock_procurement, {})

    service.procurement_repo.save_procurement_version.assert_not_called()


def test_pre_analyze_procurement_no_supported_files(mock_dependencies: dict, mock_procurement: Procurement) -> None:
    """Test _pre_analyze_procurement when no supported files are found."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.process_procurement_documents.return_value = [("file.txt", b"content")]
    service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)

    service._pre_analyze_procurement(mock_procurement, {})

    service.procurement_repo.save_procurement_version.assert_not_called()
    service.analysis_repo.save_pre_analysis.assert_not_called()


def test_run_pre_analysis_happy_path(mock_dependencies: dict, mock_procurement: Procurement) -> None:
    """Test the happy path for run_pre_analysis."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = [(mock_procurement, {})]

    with patch.object(service, "_pre_analyze_procurement") as mock_pre_analyze:
        service.run_pre_analysis(date(2025, 1, 1), date(2025, 1, 1), 10, 0)
        mock_pre_analyze.assert_called_once_with(mock_procurement, {})


def test_run_pre_analysis_max_messages(mock_dependencies: dict, mock_procurement: Procurement) -> None:
    """Test that run_pre_analysis stops when max_messages is reached."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = [
        (mock_procurement, {}),
        (mock_procurement, {}),
    ]

    with patch.object(service, "_pre_analyze_procurement") as mock_pre_analyze:
        service.run_pre_analysis(date(2025, 1, 1), date(2025, 1, 1), 10, 0, max_messages=1)
        assert mock_pre_analyze.call_count == 1


@patch("public_detective.services.analysis.PricingService")
def test_pre_analyze_procurement_happy_path(
    mock_pricing_service: MagicMock, mock_dependencies: dict, mock_procurement: Procurement
) -> None:
    """Test the happy path for _pre_analyze_procurement."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_procurement_by_hash.return_value = None
    service.procurement_repo.get_latest_version.return_value = 1
    # Mock the return value for the new logic in _select_and_prepare_files_for_ai
    service.ai_provider.count_tokens_for_analysis.return_value = (100, 0, 0)
    mock_pricing_service.return_value.calculate.return_value = (
        MagicMock(),
        MagicMock(),
        MagicMock(),
        MagicMock(),
    )

    service._pre_analyze_procurement(mock_procurement, {})

    service.procurement_repo.save_procurement_version.assert_called_once()
    service.analysis_repo.save_pre_analysis.assert_called_once()
    call_kwargs = service.analysis_repo.save_pre_analysis.call_args[1]
    assert call_kwargs["input_tokens_used"] == 100
    assert call_kwargs["output_tokens_used"] == 0
    assert call_kwargs["thinking_tokens_used"] == 0
    service.status_history_repo.create_record.assert_called_once()


def test_pre_analyze_procurement_no_files(mock_dependencies: dict, mock_procurement: Procurement) -> None:
    """Test _pre_analyze_procurement when no files are found."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.process_procurement_documents.return_value = []
    service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)

    service._pre_analyze_procurement(mock_procurement, {})

    service.procurement_repo.save_procurement_version.assert_not_called()
