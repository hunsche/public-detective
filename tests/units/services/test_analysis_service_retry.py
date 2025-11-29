from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.models.procurements import Procurement
from public_detective.models.source_documents import SourceDocument
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
    service.file_type_provider = MagicMock()
    service.image_converter_provider = MagicMock()
    service.converter_service = MagicMock()
    service.pricing_service = MagicMock()
    service.ranking_service = MagicMock()
    service.config = MagicMock()
    service.config.GCP_GEMINI_MAX_OUTPUT_TOKENS = 1000
    service.config.GCP_GEMINI_MAX_INPUT_TOKENS = 10000
    service.config.GCP_GCS_BUCKET_PROCUREMENTS = "bucket"
    return service


def test_retry_analyses_resume_pre_analysis(analysis_service: AnalysisService) -> None:
    """Tests retry_analyses resuming a pending pre-analysis."""
    analysis_id = uuid4()
    analysis = MagicMock(
        analysis_id=analysis_id,
        procurement_control_number="123",
        version_number=1,
        status=ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value,
        updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        retry_count=0,
    )
    analysis_service.analysis_repo.get_analyses_to_retry.return_value = [analysis]

    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "123"
    procurement.version_number = 1
    procurement.entity_unit = MagicMock(ibge_code="1234567", unit_name="Test Unit")
    procurement.object_description = "Test Object"
    gov_entity = MagicMock()
    gov_entity.name = "Test Entity"
    procurement.government_entity = gov_entity
    procurement.modality = 1
    procurement.total_estimated_value = Decimal("1000.00")
    procurement.proposal_closing_date = datetime.now(timezone.utc)
    procurement.proposal_opening_date = datetime.now(timezone.utc)

    analysis_service.procurement_repo.get_procurement_by_id_and_version.return_value = procurement

    # Mock file records for _rebuild_candidates_from_db
    file_record = {
        "file_record_id": uuid4(),
        "source_document_id": uuid4(),
        "file_name": "test.pdf",
        "gcs_path": "path/to/test.pdf",
        "prepared_content_gcs_uris": ["gs://bucket/test.pdf"],
        "exclusion_reason": None,
    }
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = [file_record]

    source_doc = MagicMock(spec=SourceDocument)
    source_doc.id = file_record["source_document_id"]
    source_doc.synthetic_id = "syn_id"
    source_doc.raw_metadata = {}
    analysis_service.source_document_repo.get_source_documents_by_ids.return_value = [source_doc]

    analysis_service.ai_provider.count_tokens_for_analysis.return_value = (100, 0, 0)
    analysis_service.pricing_service.calculate_total_cost.return_value = (
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.04"),
    )

    analysis_service.file_type_provider.get_file_type.return_value = "PDF"

    retried_count = analysis_service.retry_analyses(initial_backoff_hours=1, max_retries=3, timeout_hours=24)

    assert retried_count == 1
    analysis_service.analysis_repo.update_pre_analysis_with_tokens.assert_called_once()
    analysis_service.ranking_service.calculate_priority.assert_called_once()


def test_retry_analyses_retry_failed_analysis_copy_files(analysis_service: AnalysisService) -> None:
    """Tests retry_analyses retrying a failed analysis by copying files."""
    analysis_id = uuid4()
    analysis = MagicMock(
        analysis_id=analysis_id,
        procurement_control_number="123",
        version_number=1,
        status=ProcurementAnalysisStatus.ANALYSIS_FAILED.value,
        updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        retry_count=0,
        input_tokens_used=100,
        output_tokens_used=100,
        thinking_tokens_used=0,
        search_queries_used=0,
        analysis_prompt="prompt",
        document_hash="hash",
    )
    analysis_service.analysis_repo.get_analyses_to_retry.return_value = [analysis]

    new_analysis_id = uuid4()
    analysis_service.analysis_repo.save_retry_analysis.return_value = new_analysis_id

    analysis_service.pricing_service.calculate_total_cost.return_value = (
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.04"),
    )

    # Mock files for _copy_files_to_retry_analysis
    old_source_doc = MagicMock(spec=SourceDocument)
    old_source_doc.id = uuid4()
    old_source_doc.synthetic_id = "syn_id"
    old_source_doc.title = "Title"
    old_source_doc.publication_date = datetime.now(timezone.utc)
    old_source_doc.document_type_name = "Type"
    old_source_doc.url = "http://url"
    old_source_doc.raw_metadata = {}
    analysis_service.source_document_repo.get_source_documents_by_analysis_id.return_value = [old_source_doc]

    old_file_record = {
        "source_document_id": old_source_doc.id,
        "file_name": "test.pdf",
        "gcs_path": "path/test.pdf",
        "extension": "pdf",
        "size_bytes": 100,
        "nesting_level": 0,
        "included_in_analysis": True,
        "exclusion_reason": None,
        "prioritization_logic": "NO_PRIORITY",
        "prioritization_keyword": None,
        "applied_token_limit": None,
        "prepared_content_gcs_uris": ["gs://bucket/test.pdf"],
        "raw_document_metadata": {},
        "inferred_extension": "pdf",
        "used_fallback_conversion": False,
    }
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = [old_file_record]

    analysis_service.source_document_repo.save_source_document.return_value = uuid4()

    retried_count = analysis_service.retry_analyses(initial_backoff_hours=1, max_retries=3, timeout_hours=24)

    assert retried_count == 1
    analysis_service.analysis_repo.save_retry_analysis.assert_called_once()
    analysis_service.source_document_repo.save_source_document.assert_called_once()
    analysis_service.file_record_repo.save_file_record.assert_called_once()


def test_retry_analyses_retry_failed_analysis_redownload(analysis_service: AnalysisService) -> None:
    """Tests retry_analyses retrying a failed analysis by re-downloading files."""
    analysis_id = uuid4()
    analysis = MagicMock(
        analysis_id=analysis_id,
        procurement_control_number="123",
        version_number=1,
        status=ProcurementAnalysisStatus.ANALYSIS_FAILED.value,
        updated_at=datetime.now(timezone.utc) - timedelta(hours=2),
        retry_count=0,
        input_tokens_used=100,
        output_tokens_used=100,
        thinking_tokens_used=0,
        search_queries_used=0,
        analysis_prompt="prompt",
        document_hash="hash",
    )
    analysis_service.analysis_repo.get_analyses_to_retry.return_value = [analysis]

    new_analysis_id = uuid4()
    analysis_service.analysis_repo.save_retry_analysis.return_value = new_analysis_id

    analysis_service.pricing_service.calculate_total_cost.return_value = (
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.01"),
        Decimal("0.04"),
    )

    # Mock NO files for _copy_files_to_retry_analysis
    analysis_service.source_document_repo.get_source_documents_by_analysis_id.return_value = []
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = []

    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "123"
    procurement.version_number = 1
    procurement.entity_unit = MagicMock(ibge_code="1234567", unit_name="Test Unit")
    procurement.object_description = "Test Object"
    gov_entity = MagicMock()
    gov_entity.name = "Test Entity"
    procurement.government_entity = gov_entity
    procurement.modality = 1
    procurement.total_estimated_value = Decimal("1000.00")
    procurement.proposal_closing_date = datetime.now(timezone.utc)
    procurement.proposal_opening_date = datetime.now(timezone.utc)

    analysis_service.procurement_repo.get_procurement_by_id_and_version.return_value = procurement
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid4()

    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        relative_path="test.pdf",
        content=b"content",
        raw_document_metadata={"sequencialDocumento": 1},
        extraction_failed=False,
    )
    analysis_service.procurement_repo.process_procurement_documents.return_value = [processed_file]

    analysis_service.file_type_provider.get_file_type.return_value = "PDF"
    analysis_service.gcs_provider.upload_content.return_value = "gs://bucket/test.pdf"
    analysis_service.ai_provider.count_tokens_for_analysis.return_value = (100, 0, 0)

    # Mock _process_and_save_source_documents to return a map with valid UUIDs
    source_doc_id = uuid4()

    with patch.object(analysis_service, "_process_and_save_source_documents", return_value={"syn_id": source_doc_id}):
        # Mock _prepare_ai_candidates to return a candidate with known synthetic_id
        candidate = MagicMock()
        candidate.synthetic_id = "syn_id"
        candidate.ai_path = "test.pdf"
        candidate.ai_content = b"content"
        candidate.is_included = True
        candidate.exclusion_reason = None
        candidate.ai_gcs_uris = ["gs://bucket/test.pdf"]
        candidate.original_path = "test.pdf"
        candidate.original_content = b"content"
        candidate.inferred_extension = "pdf"
        candidate.applied_token_limit = None

        with patch.object(analysis_service, "_prepare_ai_candidates", return_value=[candidate]):
            retried_count = analysis_service.retry_analyses(initial_backoff_hours=1, max_retries=3, timeout_hours=24)

    assert retried_count == 1
    analysis_service.procurement_repo.process_procurement_documents.assert_called_once()
    analysis_service.gcs_provider.upload_file.assert_called()
