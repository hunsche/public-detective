from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from public_detective.models.procurements import Procurement
from public_detective.repositories.procurements import ProcessedFile
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


def test_run_pre_analysis_by_control_number_success(analysis_service: AnalysisService) -> None:
    """Tests run_pre_analysis_by_control_number success flow."""
    control_number = "12345678901234-1-1/2024"
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = control_number
    procurement.entity_unit = MagicMock(ibge_code="1234567", unit_name="Test Unit")
    procurement.object_description = "Test Object"
    gov_entity = MagicMock()
    gov_entity.name = "Test Entity"
    procurement.government_entity = gov_entity
    procurement.modality = 1
    procurement.total_estimated_value = Decimal("1000.00")
    procurement.proposal_closing_date = datetime.now(timezone.utc)
    procurement.proposal_opening_date = datetime.now(timezone.utc)
    procurement.process_number = "123/2024"
    procurement.procurement_number = "123/2024"
    procurement.procurement_year = 2024
    procurement.procurement_sequence = 1
    procurement.pncp_publication_date = datetime.now(timezone.utc)
    procurement.last_update_date = datetime.now(timezone.utc)
    procurement.global_update_date = datetime.now(timezone.utc)
    procurement.dispute_method = 1
    procurement.procurement_status = 1
    procurement.user_name = "User"
    procurement.electronic_process_link = "http://link"
    procurement.in_person_justification = None
    procurement.budgetary_sources = []
    procurement.additional_information = None
    procurement.source_system_link = None
    procurement.legal_support = MagicMock(code=1, name="Lei", description="Desc")
    procurement.total_awarded_value = None
    procurement.is_srp = False
    procurement.version_number = 1
    procurement.content_hash = "hash"

    raw_data = {"key": "value"}

    analysis_service.procurement_repo.get_procurement_by_control_number.return_value = (procurement, raw_data)

    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        relative_path="test.pdf",
        content=b"content",
        raw_document_metadata={
            "sequencialDocumento": 1,
            "titulo": "Test Doc",
            "dataPublicacaoPncp": "2024-01-01",
            "tipoDocumentoId": 1,
        },
        extraction_failed=False,
    )
    analysis_service.procurement_repo.process_procurement_documents.return_value = [processed_file]

    analysis_service.procurement_repo.get_procurement_by_hash.return_value = None
    analysis_service.procurement_repo.get_latest_version.return_value = 0
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid4()
    analysis_service.analysis_repo.create_pre_analysis_record.return_value = uuid4()
    analysis_service.source_document_repo.save_source_document.return_value = uuid4()

    analysis_service.file_type_provider.get_file_type.return_value = "PDF"
    analysis_service.gcs_provider.upload_content.return_value = "gs://bucket/test.pdf"

    analysis_service.ai_provider.count_tokens_for_analysis.return_value = (100, 0, 0)
    analysis_service.pricing_service.calculate_total_cost.return_value = (
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.04"),
    )

    # Mock ranking service
    analysis_service.ranking_service.calculate_priority.return_value = procurement

    # Run the generator
    events = list(analysis_service.run_pre_analysis_by_control_number(control_number))

    assert len(events) > 0
    assert events[-1][0] == "procurement_processed"

    analysis_service.procurement_repo.process_procurement_documents.assert_called_once()
    analysis_service.procurement_repo.save_procurement_version.assert_called_once()
    analysis_service.analysis_repo.create_pre_analysis_record.assert_called_once()
    analysis_service.source_document_repo.save_source_document.assert_called()
    analysis_service.file_record_repo.save_file_record.assert_called()
    analysis_service.analysis_repo.update_pre_analysis_with_tokens.assert_called_once()
    analysis_service.ranking_service.calculate_priority.assert_called_once()
    analysis_service.procurement_repo.update_procurement_ranking_data.assert_called_once()
    analysis_service.analysis_repo.update_analysis_status.assert_called()


def test_run_pre_analysis_by_control_number_not_found(analysis_service: AnalysisService) -> None:
    """Tests run_pre_analysis_by_control_number when procurement is not found."""
    analysis_service.procurement_repo.get_procurement_by_control_number.return_value = (None, None)

    events = list(analysis_service.run_pre_analysis_by_control_number("123"))

    assert len(events) == 1
    assert events[0][0] == "day_started"
    # Should log error and return
    analysis_service.procurement_repo.process_procurement_documents.assert_not_called()
