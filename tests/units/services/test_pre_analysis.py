"""Unit tests for the pre-analysis service functions."""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from public_detective.models.procurements import Procurement
from public_detective.providers.ai import AiProvider
from public_detective.providers.gcs import GcsProvider
from public_detective.providers.pubsub import PubSubProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.repositories.budget_ledger import BudgetLedgerRepository
from public_detective.repositories.file_records import FileRecordsRepository
from public_detective.repositories.procurements import ProcurementsRepository
from public_detective.repositories.source_documents import SourceDocumentsRepository
from public_detective.repositories.status_history import StatusHistoryRepository
from public_detective.services.analysis import AnalysisService


@pytest.fixture
def mock_dependencies() -> dict:
    """Fixture to create mock dependencies for the AnalysisService."""
    return {
        "procurement_repo": MagicMock(spec=ProcurementsRepository),
        "analysis_repo": MagicMock(spec=AnalysisRepository),
        "source_document_repo": MagicMock(spec=SourceDocumentsRepository),
        "file_record_repo": MagicMock(spec=FileRecordsRepository),
        "status_history_repo": MagicMock(spec=StatusHistoryRepository),
        "budget_ledger_repo": MagicMock(spec=BudgetLedgerRepository),
        "ai_provider": MagicMock(spec=AiProvider),
        "gcs_provider": MagicMock(spec=GcsProvider),
        "pubsub_provider": MagicMock(spec=PubSubProvider),
    }


def test_run_pre_analysis_happy_path(mock_dependencies: dict, mock_procurement: Procurement) -> None:
    """Test the happy path for run_pre_analysis."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = [(mock_procurement, {})]
    service.procurement_repo.get_latest_version.return_value = 0
    service.procurement_repo.get_procurement_by_hash.return_value = False
    service.analysis_repo.save_pre_analysis.return_value = "new-analysis-id"

    with patch.object(service, "_pre_analyze_procurement") as mock_pre_analyze:
        # Consume the generator to trigger the logic
        list(service.run_pre_analysis(date(2025, 1, 1), date(2025, 1, 1), 100, 60, None))
        mock_pre_analyze.assert_called_once()


def test_run_pre_analysis_no_procurements_found(mock_dependencies: dict) -> None:
    """Tests that the pre-analysis job handles dates with no procurements."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = []
    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 1)

    # Consume the generator to trigger the logic
    list(service.run_pre_analysis(start_date, end_date, 100, 60, None))

    service.procurement_repo.get_updated_procurements_with_raw_data.assert_called_once_with(target_date=start_date)
    service.analysis_repo.save_pre_analysis.assert_not_called()


def test_pre_analyze_procurement_idempotency(mock_dependencies: dict, mock_procurement: Procurement) -> None:
    """
    Tests that _pre_analyze_procurement skips processing if a procurement
    with the same hash already exists.
    """
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_procurement_by_hash.return_value = True
    service.procurement_repo.process_procurement_documents.return_value = []

    service._pre_analyze_procurement(mock_procurement, {})

    service.procurement_repo.save_procurement_version.assert_not_called()
    service.analysis_repo.save_pre_analysis.assert_not_called()


def test_pre_analyze_procurement_existing_hash(mock_dependencies: dict, mock_procurement: Procurement) -> None:
    """Tests that pre-analysis is skipped if a procurement with the same content hash already exists."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.process_procurement_documents.return_value = []
    service.procurement_repo.get_procurement_by_hash.return_value = True

    with (
        patch.object(service, "_prepare_ai_candidates", return_value=[]),
        patch.object(service, "_select_files_by_token_limit", return_value=([], [])),
        patch.object(service, "logger") as mock_logger,
    ):
        service._pre_analyze_procurement(mock_procurement, {})
        # The exact hash depends on the mock_procurement, so we check that the log message contains the key phrase.
        assert any("already exists. Skipping." in call.args[0] for call in mock_logger.info.call_args_list)

    service.procurement_repo.save_procurement_version.assert_not_called()
