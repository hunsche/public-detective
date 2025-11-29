from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.analyses import Analysis
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.models.procurements import Procurement
from public_detective.services.analysis import AnalysisService


@pytest.fixture
def analysis_service() -> AnalysisService:
    """Creates an AnalysisService instance with mocked dependencies."""
    procurement_repo = MagicMock()
    analysis_repo = MagicMock()
    source_document_repo = MagicMock()
    file_record_repo = MagicMock()
    status_history_repo = MagicMock()
    budget_ledger_repo = MagicMock()
    ai_provider = MagicMock()
    gcs_provider = MagicMock()
    http_provider = MagicMock()
    pubsub_provider = MagicMock()

    service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        source_document_repo=source_document_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
        http_provider=http_provider,
        pubsub_provider=pubsub_provider,
    )
    # Mock internal providers
    service.file_type_provider = MagicMock()
    service.image_converter_provider = MagicMock()
    service.converter_service = MagicMock()
    service.pricing_service = MagicMock()
    service.ranking_service = MagicMock()
    return service


def test_analyze_procurement_happy_path(analysis_service: AnalysisService) -> None:
    """Tests the happy path of analyze_procurement."""
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "12345678901234-1-1/2024"
    procurement.entity_unit = MagicMock(ibge_code="1234567", unit_name="Test Unit")
    procurement.object_description = "Test Object"
    gov_entity = MagicMock()
    gov_entity.name = "Test Entity"
    procurement.government_entity = gov_entity
    procurement.modality = 1
    procurement.total_estimated_value = Decimal("1000.00")
    procurement.proposal_closing_date = datetime.now(timezone.utc)
    procurement.proposal_opening_date = datetime.now(timezone.utc)
    version_number = 1
    analysis_id = uuid4()
    procurement_id = uuid4()

    analysis_service.procurement_repo.get_procurement_uuid.return_value = procurement_id

    file_record = {
        "source_document_id": uuid4(),
        "file_name": "test.pdf",
        "included_in_analysis": True,
        "prepared_content_gcs_uris": ["gs://bucket/test.pdf"],
        "raw_document_metadata": {},
        "original_filename": "test.pdf",
        "extension": "pdf",
    }
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = [file_record]

    analysis_service.ai_provider.get_structured_analysis.return_value = (
        Analysis(
            risk_score=50,
            risk_score_rationale="Rationale",
            procurement_summary="Summary",
            analysis_summary="Analysis Summary",
            red_flags=[],
            seo_keywords=["keyword"],
        ),  # ai_analysis
        100,  # input_tokens
        50,  # output_tokens
        10,  # thinking_tokens
        {"search_queries": [], "sources": []},  # raw_grounding_metadata
        "thoughts",  # thoughts
    )

    analysis_service.pricing_service.calculate_total_cost.return_value = (
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.04"),
    )

    analysis_service.analysis_repo.get_analysis_by_id.return_value = MagicMock(document_hash="hash")

    analysis_service.analyze_procurement(procurement, version_number, analysis_id)

    analysis_service.ai_provider.get_structured_analysis.assert_called_once()
    analysis_service.analysis_repo.save_analysis.assert_called_once()
    analysis_service.budget_ledger_repo.save_expense.assert_called_once()


def test_analyze_procurement_no_file_records(analysis_service: AnalysisService) -> None:
    """Tests analyze_procurement when no file records are found."""
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "12345678901234-1-1/2024"
    procurement.object_description = "Test Object"
    gov_entity = MagicMock()
    gov_entity.name = "Test Entity"
    procurement.government_entity = gov_entity
    procurement.entity_unit = MagicMock(unit_name="Test Unit")
    procurement.modality = 1
    procurement.total_estimated_value = Decimal("1000.00")
    procurement.proposal_closing_date = datetime.now(timezone.utc)
    procurement.proposal_opening_date = datetime.now(timezone.utc)
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid4()
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = []

    # Mock AI provider response
    analysis_service.ai_provider.get_structured_analysis.return_value = (
        MagicMock(spec=Analysis),  # ai_analysis
        100,  # input_tokens
        50,  # output_tokens
        10,  # thinking_tokens
        {"search_queries": [], "sources": []},  # raw_grounding_metadata
        "thoughts",  # thoughts
    )

    # Mock analysis repo response
    analysis_service.analysis_repo.get_analysis_by_id.return_value = MagicMock(document_hash="hash")

    # Mock pricing service response
    analysis_service.pricing_service.calculate_total_cost.return_value = (
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.04"),
    )

    analysis_service.analyze_procurement(procurement, 1, uuid4())

    analysis_service.ai_provider.get_structured_analysis.assert_called_once()
    analysis_service.analysis_repo.save_analysis.assert_called_once()


def test_analyze_procurement_no_included_records(analysis_service: AnalysisService) -> None:
    """Tests analyze_procurement when no files are included."""
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "12345678901234-1-1/2024"
    procurement.object_description = "Test Object"
    gov_entity = MagicMock()
    gov_entity.name = "Test Entity"
    procurement.government_entity = gov_entity
    procurement.entity_unit = MagicMock(unit_name="Test Unit")
    procurement.modality = 1
    procurement.total_estimated_value = Decimal("1000.00")
    procurement.proposal_closing_date = datetime.now(timezone.utc)
    procurement.proposal_opening_date = datetime.now(timezone.utc)
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid4()
    file_record = {"included_in_analysis": False}
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = [file_record]

    # Mock AI provider response
    analysis_service.ai_provider.get_structured_analysis.return_value = (
        MagicMock(spec=Analysis),  # ai_analysis
        100,  # input_tokens
        50,  # output_tokens
        10,  # thinking_tokens
        {"search_queries": [], "sources": []},  # raw_grounding_metadata
        "thoughts",  # thoughts
    )

    # Mock analysis repo response
    analysis_service.analysis_repo.get_analysis_by_id.return_value = MagicMock(document_hash="hash")

    # Mock pricing service response
    analysis_service.pricing_service.calculate_total_cost.return_value = (
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.04"),
    )

    analysis_service.analyze_procurement(procurement, 1, uuid4())

    analysis_service.ai_provider.get_structured_analysis.assert_called_once()
    analysis_service.analysis_repo.save_analysis.assert_called_once()


def test_analyze_procurement_ai_error(analysis_service: AnalysisService) -> None:
    """Tests analyze_procurement when AI provider fails."""
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "12345678901234-1-1/2024"
    procurement.object_description = "Test Object"
    gov_entity = MagicMock()
    gov_entity.name = "Test Entity"
    procurement.government_entity = gov_entity
    procurement.entity_unit = MagicMock(unit_name="Test Unit")
    procurement.modality = 1
    procurement.total_estimated_value = Decimal("1000.00")
    procurement.proposal_closing_date = datetime.now(timezone.utc)
    procurement.proposal_opening_date = datetime.now(timezone.utc)

    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid4()
    file_record = {
        "included_in_analysis": True,
        "prepared_content_gcs_uris": ["gs://bucket/test.pdf"],
    }
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = [file_record]
    analysis_service.ai_provider.get_structured_analysis.side_effect = ValueError("AI Error")

    with pytest.raises(AnalysisError, match="AI Model Error"):
        analysis_service.analyze_procurement(procurement, 1, uuid4())


def test_process_analysis_from_message_success(analysis_service: AnalysisService) -> None:
    """Tests process_analysis_from_message success flow."""
    analysis_id = uuid4()
    analysis = MagicMock()
    analysis.procurement_control_number = "12345678901234-1-1/2024"
    analysis.version_number = 1

    analysis_service.analysis_repo.get_analysis_by_id.return_value = analysis
    analysis_service.procurement_repo.get_procurement_by_id_and_version.return_value = MagicMock(spec=Procurement)

    with patch.object(analysis_service, "analyze_procurement") as mock_analyze:
        analysis_service.process_analysis_from_message(analysis_id)
        mock_analyze.assert_called_once()

    analysis_service.analysis_repo.update_analysis_status.assert_called_with(
        analysis_id, ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL
    )


def test_process_analysis_from_message_analysis_not_found(analysis_service: AnalysisService) -> None:
    """Tests process_analysis_from_message when analysis is not found."""
    analysis_service.analysis_repo.get_analysis_by_id.return_value = None
    analysis_service.process_analysis_from_message(uuid4())
    # Should log error and return, not raise
    analysis_service.analysis_repo.update_analysis_status.assert_not_called()


def test_process_analysis_from_message_procurement_not_found(analysis_service: AnalysisService) -> None:
    """Tests process_analysis_from_message when procurement is not found."""
    analysis = MagicMock()
    analysis_service.analysis_repo.get_analysis_by_id.return_value = analysis
    analysis_service.procurement_repo.get_procurement_by_id_and_version.return_value = None

    analysis_service.process_analysis_from_message(uuid4())
    # Should log error and return
    analysis_service.analysis_repo.update_analysis_status.assert_not_called()


def test_process_analysis_from_message_failure(analysis_service: AnalysisService) -> None:
    """Tests process_analysis_from_message when analysis fails."""
    analysis_id = uuid4()
    analysis = MagicMock()
    analysis_service.analysis_repo.get_analysis_by_id.return_value = analysis
    analysis_service.procurement_repo.get_procurement_by_id_and_version.return_value = MagicMock(spec=Procurement)

    with patch.object(analysis_service, "analyze_procurement", side_effect=Exception("Pipeline failed")):
        with pytest.raises(AnalysisError, match="Failed to process analysis"):
            analysis_service.process_analysis_from_message(analysis_id)

    analysis_service.analysis_repo.update_analysis_status.assert_called_with(
        analysis_id, ProcurementAnalysisStatus.ANALYSIS_FAILED
    )
