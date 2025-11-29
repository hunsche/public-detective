from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.candidates import AIFileCandidate
from public_detective.models.file_records import ExclusionReason, PrioritizationLogic
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.providers.file_type import SPECIALIZED_IMAGE
from public_detective.services.analysis import AnalysisService


@pytest.fixture
def procurement_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def analysis_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def source_document_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def file_record_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def status_history_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def budget_ledger_repo() -> MagicMock:
    return MagicMock()


@pytest.fixture
def ai_provider() -> MagicMock:
    return MagicMock()


@pytest.fixture
def gcs_provider() -> MagicMock:
    return MagicMock()


@pytest.fixture
def http_provider() -> MagicMock:
    return MagicMock()


@pytest.fixture
def pubsub_provider() -> MagicMock:
    return MagicMock()


@pytest.fixture
def analysis_service(
    procurement_repo: MagicMock,
    analysis_repo: MagicMock,
    source_document_repo: MagicMock,
    file_record_repo: MagicMock,
    status_history_repo: MagicMock,
    budget_ledger_repo: MagicMock,
    ai_provider: MagicMock,
    gcs_provider: MagicMock,
    http_provider: MagicMock,
    pubsub_provider: MagicMock,
) -> AnalysisService:
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
    service.pricing_service = MagicMock()
    service.logger = MagicMock()
    service.ranking_service = MagicMock()
    service.converter_service = MagicMock()
    service.file_type_provider = MagicMock()
    service.image_converter_provider = MagicMock()
    return service


def test_process_analysis_from_message_analysis_record_not_found(
    analysis_service: AnalysisService, analysis_repo: MagicMock
) -> None:
    """Test process_analysis_from_message raises AnalysisError when record is missing on second check."""
    analysis_id = uuid4()
    # First call returns object, second call returns None
    analysis_repo.get_analysis_by_id.side_effect = [MagicMock(), None]

    with pytest.raises(AnalysisError, match=f"Analysis record {analysis_id} not found"):
        analysis_service.process_analysis_from_message(analysis_id)


def test_resolve_redirects_no_redirect_needed(analysis_service: AnalysisService) -> None:
    """Test _resolve_redirects returns original URL if not a tracking URL."""
    url = "http://example.com/normal-page"
    assert analysis_service._resolve_redirects(url) == url


def test_process_grounding_metadata_missing_original_url(analysis_service: AnalysisService) -> None:
    """Test _process_grounding_metadata skips sources without original_url."""
    raw_metadata = {"search_queries": [], "sources": [{"title": "Source 1"}]}  # Missing original_url
    result = analysis_service._process_grounding_metadata(raw_metadata)
    assert len(result.sources) == 0


def test_analyze_procurement_no_prepared_content_uris(
    analysis_service: AnalysisService,
    procurement_repo: MagicMock,
    analysis_repo: MagicMock,
    file_record_repo: MagicMock,
) -> None:
    """Test analyze_procurement logs warning when included records have no prepared content."""
    analysis_id = uuid4()
    procurement = MagicMock()
    procurement.pncp_control_number = "123"
    procurement.total_estimated_value = Decimal("1000")
    procurement.proposal_opening_date = datetime.now()
    procurement.proposal_closing_date = datetime.now()
    procurement.government_entity.name = "entity"
    procurement.entity_unit.unit_name = "unit"
    procurement.object_description = "desc"
    procurement.modality = "mod"
    version = 1

    analysis_repo.get_analysis_by_id.return_value = MagicMock(
        procurement_control_number="123", version_number=1, document_hash="hash"
    )
    procurement_repo.get_procurement_uuid.return_value = uuid4()

    # Included record but no prepared_content_gcs_uris
    file_record_repo.get_all_file_records_by_analysis_id.return_value = [
        {
            "included_in_analysis": True,
            "prepared_content_gcs_uris": [],
            "source_document_id": str(uuid4()),
            "original_filename": "test.pdf",
        }
    ]

    # Mock AI provider to return something so it doesn't fail later
    analysis_service.ai_provider.get_structured_analysis.return_value = ({}, 100, 100, 0, {}, "thoughts")
    analysis_service.pricing_service.calculate_total_cost.return_value = (0, 0, 0, 0, 0)

    with patch.object(analysis_service.logger, "warning") as mock_warn:
        analysis_service.analyze_procurement(procurement, version, analysis_id)
        mock_warn.assert_any_call(
            f"No prepared content URIs found for {procurement.pncp_control_number} despite having included records."
        )


def test_prepare_ai_candidates_fallback_conversion_failure(analysis_service: AnalysisService) -> None:
    """Test _prepare_ai_candidates handles fallback conversion failures."""
    processed_file = MagicMock()
    processed_file.relative_path = "test.xyz"
    processed_file.content = b"content"
    processed_file.extraction_failed = False
    processed_file.source_document_id = "123"
    processed_file.raw_document_metadata = {}

    analysis_service.file_type_provider.get_file_type = MagicMock(return_value="unknown")
    analysis_service.file_type_provider.infer_extension = MagicMock(return_value=".pdf")  # Supported for conversion
    analysis_service.converter_service.is_supported_for_conversion = MagicMock(return_value=True)

    # Fail both conversions
    analysis_service.converter_service.convert_to_pdf.side_effect = Exception("Primary fail")
    analysis_service.image_converter_provider.to_png.side_effect = Exception("Secondary fail")

    candidates = analysis_service._prepare_ai_candidates([processed_file])

    assert len(candidates) == 1
    assert candidates[0].exclusion_reason == ExclusionReason.CONVERSION_FAILED


def test_prepare_ai_candidates_inferred_extension_supported(analysis_service: AnalysisService) -> None:
    """Test _prepare_ai_candidates handles supported inferred extension."""
    processed_file = MagicMock()
    processed_file.relative_path = "test.xyz"
    processed_file.content = b"content"
    processed_file.extraction_failed = False
    processed_file.source_document_id = "123"
    processed_file.raw_document_metadata = {}

    analysis_service.file_type_provider.get_file_type = MagicMock(return_value="unknown")
    analysis_service.file_type_provider.infer_extension = MagicMock(return_value=".txt")  # Supported directly
    analysis_service.converter_service.is_supported_for_conversion = MagicMock(return_value=False)

    candidates = analysis_service._prepare_ai_candidates([processed_file])

    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".txt")


def test_prepare_ai_candidates_default_handling(analysis_service: AnalysisService) -> None:
    """Test _prepare_ai_candidates default handling for supported extensions."""
    processed_file = MagicMock()
    processed_file.relative_path = "test.pdf"
    processed_file.content = b"content"
    processed_file.extraction_failed = False
    processed_file.source_document_id = "123"
    processed_file.raw_document_metadata = {}

    candidates = analysis_service._prepare_ai_candidates([processed_file])

    assert len(candidates) == 1
    assert candidates[0].prepared_content_gcs_uris == ["test.pdf"]


def test_select_files_by_token_limit_skips_excluded(analysis_service: AnalysisService) -> None:
    """Test _select_files_by_token_limit skips candidates with exclusion reason."""
    candidate = AIFileCandidate(
        synthetic_id="1",
        raw_document_metadata={},
        original_path="test.pdf",
        exclusion_reason=ExclusionReason.EXTRACTION_FAILED,
    )
    procurement = MagicMock()
    procurement.object_description = "desc"
    procurement.modality = "mod"
    procurement.government_entity.name = "entity"
    procurement.entity_unit.unit_name = "unit"
    procurement.total_estimated_value = Decimal("1000")
    procurement.proposal_opening_date = datetime.now()
    procurement.proposal_closing_date = datetime.now()

    analysis_service._select_files_by_token_limit([candidate], procurement)

    # Should not call count_tokens_for_analysis
    analysis_service.ai_provider.count_tokens_for_analysis.assert_not_called()


def test_get_prioritization_logic_keyword(analysis_service: AnalysisService) -> None:
    """Test _get_prioritization_logic returns BY_KEYWORD when found in path."""
    candidate = AIFileCandidate(
        synthetic_id="1", raw_document_metadata={"tipoDocumentoNome": "Other"}, original_path="edital_licitacao.pdf"
    )

    logic, keyword = analysis_service._get_prioritization_logic(candidate)

    assert logic == PrioritizationLogic.BY_KEYWORD
    assert keyword == "edital"


def test_calculate_hash_list_content(analysis_service: AnalysisService) -> None:
    """Test _calculate_hash handles list of bytes content."""
    files = [("path", [b"part1", b"part2"])]
    hash_val = analysis_service._calculate_hash(files)
    assert hash_val is not None


def test_run_pre_analysis_events(analysis_service: AnalysisService, procurement_repo: MagicMock) -> None:
    """Test run_pre_analysis yields correct events."""
    start_date = date(2023, 1, 1)
    end_date = date(2023, 1, 1)

    # Mock generator events
    def mock_gen(target_date: date) -> object:
        yield "modality_started", "Pregão"
        yield "pages_total", 1
        yield "procurements_page", (MagicMock(), {})
        yield "page_fetched", 1

    procurement_repo.get_updated_procurements_with_raw_data.side_effect = mock_gen

    # Mock pre-analyze to avoid errors
    analysis_service._pre_analyze_procurement = MagicMock()

    events = list(analysis_service.run_pre_analysis(start_date, end_date, 1, 0))

    event_types = [e[0] for e in events]
    assert "day_started" in event_types
    assert "fetching_pages_started" in event_types
    assert "page_fetched" in event_types
    assert "procurements_fetched" in event_types
    assert "procurement_processed" in event_types


def test_run_pre_analysis_exception(analysis_service: AnalysisService) -> None:
    """Test run_pre_analysis raises AnalysisError on unexpected exception."""
    analysis_service.logger.info = MagicMock(side_effect=Exception("Boom"))

    with pytest.raises(AnalysisError, match="An unexpected error occurred during pre-analysis"):
        list(analysis_service.run_pre_analysis(date.today(), date.today(), 1, 0))


def test_run_pre_analysis_by_control_number_exception(
    analysis_service: AnalysisService, procurement_repo: MagicMock
) -> None:
    """Test run_pre_analysis_by_control_number raises AnalysisError on exception."""
    procurement_repo.get_procurement_by_control_number.side_effect = Exception("Boom")

    with pytest.raises(AnalysisError, match="An unexpected error occurred during pre-analysis"):
        list(analysis_service.run_pre_analysis_by_control_number("123"))


def test_run_ranked_analysis_procurement_not_found(
    analysis_service: AnalysisService, analysis_repo: MagicMock, procurement_repo: MagicMock
) -> None:
    """Test run_ranked_analysis skips if procurement not found."""
    analysis = MagicMock()
    analysis.procurement_control_number = "123"
    analysis.version_number = 1
    analysis_repo.get_pending_analyses_ranked.return_value = [analysis]
    procurement_repo.get_procurement_by_id_and_version.return_value = None

    analysis_service._calculate_auto_budget = MagicMock(return_value=Decimal("100"))

    triggered = analysis_service.run_ranked_analysis(True, "daily", 10)
    assert len(triggered) == 0


def test_run_ranked_analysis_budget_exhausted(
    analysis_service: AnalysisService, analysis_repo: MagicMock, procurement_repo: MagicMock
) -> None:
    """Test run_ranked_analysis stops when budget exhausted."""
    analysis = MagicMock()
    analysis.total_cost = Decimal("100.00")
    analysis.votes_count = 1
    analysis_repo.get_pending_analyses_ranked.return_value = [analysis]

    procurement = MagicMock()
    procurement.is_stable = True
    procurement.entity_unit.ibge_code = "123"
    procurement.current_priority_score = 100
    procurement_repo.get_procurement_by_id_and_version.return_value = procurement

    # Budget less than cost
    triggered = analysis_service.run_ranked_analysis(False, None, 10, budget=Decimal("50.00"))
    assert len(triggered) == 0


def test_run_ranked_analysis_max_messages_reached(
    analysis_service: AnalysisService, analysis_repo: MagicMock, procurement_repo: MagicMock
) -> None:
    """Test run_ranked_analysis stops when max_messages reached."""
    analysis1 = MagicMock(analysis_id=uuid4(), total_cost=Decimal("10"), votes_count=1)
    analysis2 = MagicMock(analysis_id=uuid4(), total_cost=Decimal("10"), votes_count=1)
    analysis_repo.get_pending_analyses_ranked.return_value = [analysis1, analysis2]

    procurement = MagicMock(is_stable=True)
    procurement.entity_unit.ibge_code = "123"
    procurement.current_priority_score = 100
    procurement_repo.get_procurement_by_id_and_version.return_value = procurement

    # Mock run_specific_analysis
    analysis_service.run_specific_analysis = MagicMock()

    triggered = analysis_service.run_ranked_analysis(False, None, 10, budget=Decimal("100"), max_messages=1)
    assert len(triggered) == 1


def test_run_ranked_analysis_exception_in_loop(
    analysis_service: AnalysisService, analysis_repo: MagicMock, procurement_repo: MagicMock
) -> None:
    """Test run_ranked_analysis handles exception in loop."""
    analysis = MagicMock(analysis_id=uuid4(), total_cost=Decimal("10"), votes_count=1)
    analysis_repo.get_pending_analyses_ranked.return_value = [analysis]

    procurement = MagicMock(is_stable=True)
    procurement.entity_unit.ibge_code = "123"
    procurement.current_priority_score = 100
    procurement_repo.get_procurement_by_id_and_version.return_value = procurement

    analysis_service.run_specific_analysis = MagicMock(side_effect=Exception("Boom"))

    triggered = analysis_service.run_ranked_analysis(False, None, 10, budget=Decimal("100"))
    assert len(triggered) == 0
    # Should log error but not crash
    analysis_service.logger.error.assert_called()


def test_prepare_ai_candidates_specialized_image(analysis_service: AnalysisService) -> None:
    """Test _prepare_ai_candidates handles specialized image conversion."""
    processed_file = MagicMock()
    processed_file.relative_path = "image.ai"
    processed_file.content = b"content"
    processed_file.extraction_failed = False
    processed_file.source_document_id = "123"
    processed_file.raw_document_metadata = {}

    analysis_service.file_type_provider.get_file_type.side_effect = [SPECIALIZED_IMAGE, "unknown"]
    analysis_service.file_type_provider.infer_extension.return_value = ".ai"
    analysis_service.image_converter_provider.to_png.return_value = b"png"

    candidates = analysis_service._prepare_ai_candidates([processed_file])

    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".png")
    assert candidates[0].ai_content == b"png"


def test_retry_analyses_exception_inner(analysis_service: AnalysisService, analysis_repo: MagicMock) -> None:
    """Test retry_analyses handles exception inside the loop."""
    analysis = MagicMock(analysis_id=uuid4(), retry_count=0, updated_at=datetime.now(timezone.utc) - timedelta(hours=2))
    analysis.status = ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value
    analysis_repo.get_analyses_to_retry.return_value = [analysis]

    analysis_service._resume_pre_analysis = MagicMock(side_effect=Exception("Inner Boom"))

    retried = analysis_service.retry_analyses(1, 1, 1)

    assert retried == 0
    analysis_service.logger.error.assert_called()
    analysis_service.status_history_repo.create_record.assert_called()


def test_copy_files_to_retry_analysis_enum_fallbacks(
    analysis_service: AnalysisService, source_document_repo: MagicMock, file_record_repo: MagicMock
) -> None:
    """Test _copy_files_to_retry_analysis handles invalid enum values."""
    old_id = uuid4()
    new_id = uuid4()

    old_doc = MagicMock(id=uuid4())
    old_doc.synthetic_id = "syn_id"
    old_doc.title = "Title"
    old_doc.publication_date = datetime.now()
    old_doc.document_type_name = "Type"
    old_doc.url = "http://example.com"
    old_doc.raw_metadata = {}
    source_document_repo.get_source_documents_by_analysis_id.return_value = [old_doc]
    source_document_repo.save_source_document.return_value = uuid4()

    file_record = {
        "source_document_id": old_doc.id,
        "file_name": "f",
        "gcs_path": "p",
        "extension": "e",
        "size_bytes": 1,
        "nesting_level": 1,
        "included_in_analysis": True,
        "prioritization_logic": "INVALID_LOGIC",
        "exclusion_reason": "INVALID_REASON",
        "prepared_content_gcs_uris": [],
    }
    file_record_repo.get_all_file_records_by_analysis_id.return_value = [file_record]

    analysis_service._copy_files_to_retry_analysis(old_id, new_id, "123", 1)

    # Check that save_file_record was called with NO_PRIORITY and None exclusion_reason
    call_args = analysis_service.file_record_repo.save_file_record.call_args
    new_record = call_args[0][0]
    assert new_record.prioritization_logic == PrioritizationLogic.NO_PRIORITY
    assert new_record.exclusion_reason is None


def test_retry_analyses_exception_outer(analysis_service: AnalysisService, analysis_repo: MagicMock) -> None:
    """Test retry_analyses raises AnalysisError on unexpected exception."""
    analysis_repo.get_analyses_to_retry.side_effect = Exception("Boom")

    with pytest.raises(AnalysisError, match="An unexpected error occurred during retry analyses"):
        analysis_service.retry_analyses(1, 1, 1)


def test_copy_files_to_retry_analysis_fallback_failures(
    analysis_service: AnalysisService,
    source_document_repo: MagicMock,
    file_record_repo: MagicMock,
    procurement_repo: MagicMock,
) -> None:
    """Test _copy_files_to_retry_analysis fallback paths."""
    old_id = uuid4()
    new_id = uuid4()

    # No old files
    source_document_repo.get_source_documents_by_analysis_id.return_value = []
    file_record_repo.get_all_file_records_by_analysis_id.return_value = []

    # Procurement not found
    procurement_repo.get_procurement_by_id_and_version.return_value = None

    analysis_service._copy_files_to_retry_analysis(old_id, new_id, "123", 1)

    analysis_service.logger.error.assert_called_with("Procurement 123 not found in DB. Cannot recover files.")

    # Procurement found, UUID not found
    procurement_repo.get_procurement_by_id_and_version.return_value = MagicMock()
    procurement_repo.get_procurement_uuid.return_value = None

    analysis_service._copy_files_to_retry_analysis(old_id, new_id, "123", 1)
    analysis_service.logger.error.assert_called_with("Procurement UUID not found for 123. Cannot recover files.")

    # Exception during recovery
    procurement_repo.get_procurement_uuid.return_value = uuid4()
    procurement_repo.process_procurement_documents.side_effect = Exception("Boom")

    analysis_service._copy_files_to_retry_analysis(old_id, new_id, "123", 1)
    analysis_service.logger.error.assert_called()


def test_rebuild_candidates_from_db_missing_source_doc(
    analysis_service: AnalysisService, file_record_repo: MagicMock, source_document_repo: MagicMock
) -> None:
    """Test _rebuild_candidates_from_db handles missing source document."""
    analysis_id = uuid4()
    file_record_repo.get_all_file_records_by_analysis_id.return_value = [
        {"source_document_id": str(uuid4()), "file_record_id": 1}
    ]
    source_document_repo.get_source_documents_by_ids.return_value = []

    candidates = analysis_service._rebuild_candidates_from_db(analysis_id)
    assert len(candidates) == 0
    analysis_service.logger.warning.assert_called()


def test_resume_pre_analysis_procurement_not_found(
    analysis_service: AnalysisService, procurement_repo: MagicMock
) -> None:
    """Test _resume_pre_analysis raises AnalysisError if procurement not found."""
    analysis = MagicMock(analysis_id=uuid4(), procurement_control_number="123", version_number=1)
    procurement_repo.get_procurement_by_id_and_version.return_value = None

    with pytest.raises(AnalysisError, match="Procurement not found for resuming analysis"):
        analysis_service._resume_pre_analysis(analysis)


def test_resume_pre_analysis_db_procurement_missing(
    analysis_service: AnalysisService,
    procurement_repo: MagicMock,
    file_record_repo: MagicMock,
    source_document_repo: MagicMock,
) -> None:
    """Test _resume_pre_analysis handles missing db_procurement for ranking update."""
    analysis = MagicMock(analysis_id=uuid4(), procurement_control_number="123", version_number=1)

    # First call finds procurement, second call (for ranking) returns None
    procurement = MagicMock()
    procurement_repo.get_procurement_by_id_and_version.side_effect = [procurement, None]

    # Mock other dependencies to pass
    analysis_service._rebuild_candidates_from_db = MagicMock(return_value=[])
    analysis_service._select_files_by_token_limit = MagicMock(return_value=[])
    analysis_service._build_analysis_prompt = MagicMock(return_value="prompt")
    analysis_service.ai_provider.count_tokens_for_analysis.return_value = (0, 0, 0)
    analysis_service.pricing_service.calculate_total_cost.return_value = (0, 0, 0, 0, 0)

    analysis_service._resume_pre_analysis(analysis)

    # Should complete without error, but skip ranking update
    analysis_service.ranking_service.calculate_priority.assert_not_called()
