import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from public_detective.services.analysis import AnalysisService
from public_detective.services.pricing import Modality


@pytest.fixture
def analysis_service() -> AnalysisService:
    """Provides an AnalysisService instance with mocked dependencies."""
    with (
        patch("public_detective.services.analysis.ProcurementsRepository") as mock_proc_repo,
        patch("public_detective.services.analysis.AnalysisRepository") as mock_analysis_repo,
        patch("public_detective.services.analysis.SourceDocumentsRepository") as mock_source_repo,
        patch("public_detective.services.analysis.FileRecordsRepository") as mock_file_repo,
        patch("public_detective.services.analysis.StatusHistoryRepository") as mock_history_repo,
        patch("public_detective.services.analysis.BudgetLedgerRepository") as mock_budget_repo,
        patch("public_detective.services.analysis.AiProvider") as mock_ai_provider,
        patch("public_detective.services.analysis.GcsProvider") as mock_gcs_provider,
        patch("public_detective.services.analysis.HttpProvider") as mock_http_provider,
        patch("public_detective.services.analysis.PubSubProvider") as mock_pubsub_provider,
        patch("public_detective.services.analysis.PricingService") as mock_pricing_service,
        patch("public_detective.services.analysis.RankingService") as mock_ranking_service,
    ):
        service = AnalysisService(
            procurement_repo=mock_proc_repo.return_value,
            analysis_repo=mock_analysis_repo.return_value,
            source_document_repo=mock_source_repo.return_value,
            file_record_repo=mock_file_repo.return_value,
            status_history_repo=mock_history_repo.return_value,
            budget_ledger_repo=mock_budget_repo.return_value,
            ai_provider=mock_ai_provider.return_value,
            gcs_provider=mock_gcs_provider.return_value,
            http_provider=mock_http_provider.return_value,
            pubsub_provider=mock_pubsub_provider.return_value,
        )
        # We need to explicitly set the mocked services because they are instantiated inside __init__
        # However, since we patched the classes, the instances created inside __init__ will be mocks.
        # But to access them easily in the test, we can assign the mocks we created to the service instance
        # or just rely on the fact that service.pricing_service will be the return value of the mocked class.

        # Let's explicitly set them to be sure we are controlling the right mock objects
        service.pricing_service = mock_pricing_service.return_value
        service.ranking_service = mock_ranking_service.return_value

        return service


def test_pre_analyze_procurement_uses_5_search_queries_for_estimation(
    analysis_service: AnalysisService,
) -> None:
    # Setup mocks
    procurement = MagicMock()
    procurement.pncp_control_number = "PNCP123"
    procurement.proposal_closing_date = None
    procurement.proposal_opening_date = None
    procurement.total_estimated_value = None
    procurement.object_description = "Test Object"
    procurement.modality = "Test Modality"
    procurement.government_entity.name = "Test Entity"
    procurement.entity_unit.unit_name = "Test Unit"
    raw_data = {"key": "value"}

    analysis_service.procurement_repo.process_procurement_documents.return_value = []
    analysis_service.procurement_repo.get_procurement_by_hash.return_value = None
    analysis_service.procurement_repo.get_latest_version.return_value = 1
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid.uuid4()

    analysis_id = uuid.uuid4()
    analysis_service.analysis_repo.create_pre_analysis_record.return_value = analysis_id

    analysis_service.ai_provider.count_tokens_for_analysis.return_value = (100, 0, 0)

    analysis_service.pricing_service.calculate_total_cost.return_value = (
        Decimal("0.1"),
        Decimal("0.0"),
        Decimal("0.0"),
        Decimal("0.07"),
        Decimal("0.17"),
    )

    # Execute
    analysis_service._pre_analyze_procurement(procurement, raw_data)

    # Assert
    # Check if calculate_total_cost was called with correct arguments
    # output_tokens should be GCP_GEMINI_MAX_OUTPUT_TOKENS (65536 default)
    analysis_service.pricing_service.calculate_total_cost.assert_called_once_with(
        100,
        65536,
        0,
        modality=Modality.TEXT,
        search_queries_count=10,
    )
    # Check if update_pre_analysis_with_tokens was called with search_queries_used=10
    _, kwargs = analysis_service.analysis_repo.update_pre_analysis_with_tokens.call_args
    assert kwargs["search_queries_used"] == 10
