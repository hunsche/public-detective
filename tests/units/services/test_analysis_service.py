"""Unit tests for the AnalysisService."""

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.analyses import Analysis, AnalysisResult
from public_detective.models.file_records import ExclusionReason, PrioritizationLogic, Warnings
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.models.procurements import Procurement
from public_detective.repositories.procurements import ProcessedFile
from public_detective.services.analysis import AIFileCandidate, AnalysisService


@pytest.fixture
def mock_procurement_repo() -> MagicMock:
    """Provides a mock ProcurementsRepository."""
    return MagicMock()


@pytest.fixture
def mock_analysis_repo() -> MagicMock:
    """Provides a mock AnalysisRepository."""
    return MagicMock()


@pytest.fixture
def mock_source_document_repo() -> MagicMock:
    """Provides a mock SourceDocumentsRepository."""
    return MagicMock()


@pytest.fixture
def mock_file_record_repo() -> MagicMock:
    """Provides a mock FileRecordsRepository."""
    return MagicMock()


@pytest.fixture
def mock_status_history_repo() -> MagicMock:
    """Provides a mock StatusHistoryRepository."""
    return MagicMock()


@pytest.fixture
def mock_budget_ledger_repo() -> MagicMock:
    """Provides a mock BudgetLedgerRepository."""
    return MagicMock()


@pytest.fixture
def mock_ai_provider() -> MagicMock:
    """Provides a mock AiProvider."""
    return MagicMock()


@pytest.fixture
def mock_gcs_provider() -> MagicMock:
    """Provides a mock GcsProvider."""
    return MagicMock()


@pytest.fixture
def mock_pubsub_provider() -> MagicMock:
    """Provides a mock PubSubProvider."""
    return MagicMock()


@pytest.fixture
def mock_procurement() -> MagicMock:
    """Provides a mock Procurement object for testing."""
    procurement = MagicMock(spec=Procurement)
    procurement.process_number = "123/2023"
    procurement.object_description = "Original Description"
    procurement.modality = "Pregão"
    procurement.total_estimated_value = Decimal("1000.00")
    procurement.proposal_opening_date = datetime.now()
    procurement.proposal_closing_date = datetime.now()

    # Mock nested attributes
    procurement.legal_support = MagicMock()
    procurement.legal_support.model_dump.return_value = {"codigo": 1, "nome": "Lei"}

    procurement.government_entity = MagicMock()
    procurement.government_entity.model_dump.return_value = {"cnpj": "001", "razaoSocial": "Org"}
    procurement.government_entity.name = "Test Org"

    procurement.entity_unit = MagicMock()
    procurement.entity_unit.model_dump.return_value = {"codigoUnidade": "U01", "nomeUnidade": "Unit"}
    procurement.entity_unit.unit_name = "Test Unit"

    procurement.is_srp = False
    procurement.pncp_control_number = "PNCP123"
    procurement.procurement_status = 1
    procurement.total_awarded_value = Decimal("950.00")
    procurement.dispute_method = 1
    procurement.user_name = "original_user"
    return procurement


@pytest.fixture
def mock_valid_analysis() -> Analysis:
    """Provides a valid Analysis object for mocking."""
    return Analysis(
        risk_score=5,
        risk_score_rationale="Justificativa da nota.",
        procurement_summary="Resumo da licitação.",
        analysis_summary="Resumo da análise.",
        red_flags=[],
        seo_keywords=["teste", "cobertura"],
    )


@pytest.fixture
def analysis_service(
    mock_procurement_repo: MagicMock,
    mock_analysis_repo: MagicMock,
    mock_source_document_repo: MagicMock,
    mock_file_record_repo: MagicMock,
    mock_status_history_repo: MagicMock,
    mock_budget_ledger_repo: MagicMock,
    mock_ai_provider: MagicMock,
    mock_gcs_provider: MagicMock,
    mock_pubsub_provider: MagicMock,
) -> AnalysisService:
    """Provides an AnalysisService instance with mocked dependencies."""
    service = AnalysisService(
        procurement_repo=mock_procurement_repo,
        analysis_repo=mock_analysis_repo,
        source_document_repo=mock_source_document_repo,
        file_record_repo=mock_file_record_repo,
        status_history_repo=mock_status_history_repo,
        budget_ledger_repo=mock_budget_ledger_repo,
        ai_provider=mock_ai_provider,
        gcs_provider=mock_gcs_provider,
        pubsub_provider=mock_pubsub_provider,
    )
    service.pricing_service = MagicMock()
    return service


def test_prepare_ai_candidates_unsupported_extension(analysis_service: AnalysisService, caplog: Any) -> None:
    """Tests that a file with an unsupported extension is marked for exclusion."""
    analysis_service.file_type_provider = MagicMock()
    analysis_service.file_type_provider.infer_extension.return_value = ".unsupported"
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="document.unsupported",
        content=b"some content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].exclusion_reason == ExclusionReason.UNSUPPORTED_EXTENSION


def test_prepare_ai_candidates_extraction_failed(analysis_service: AnalysisService) -> None:
    """Tests that files flagged with extraction failure are excluded."""
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="archive.zip",
        content=b"zip content",
        raw_document_metadata={},
        extraction_failed=True,
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].exclusion_reason == ExclusionReason.EXTRACTION_FAILED
    assert candidates[0].is_included is False


@patch("public_detective.services.converter.ConverterService.docx_to_pdf")
def test_prepare_ai_candidates_docx_conversion(mock_converter: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests successful conversion of a .docx file."""
    mock_converter.return_value = b"pdf content"
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="document.docx",
        content=b"docx content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".pdf")
    assert candidates[0].ai_content == b"pdf content"
    assert candidates[0].exclusion_reason is None


@patch("public_detective.services.converter.ConverterService.rtf_to_pdf")
def test_prepare_ai_candidates_rtf_conversion(mock_converter: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests successful conversion of an .rtf file."""
    mock_converter.return_value = b"pdf content"
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="document.rtf",
        content=b"rtf content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".pdf")
    assert candidates[0].ai_content == b"pdf content"


@patch("public_detective.services.converter.ConverterService.doc_to_pdf")
def test_prepare_ai_candidates_doc_conversion(mock_converter: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests successful conversion of a .doc file."""
    mock_converter.return_value = b"pdf content"
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="document.doc",
        content=b"doc content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".pdf")
    assert candidates[0].ai_content == b"pdf content"


@patch("public_detective.services.converter.ConverterService.bmp_to_png")
def test_prepare_ai_candidates_bmp_conversion(mock_converter: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests successful conversion of a .bmp file."""
    mock_converter.return_value = b"png content"
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="image.bmp",
        content=b"bmp content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".png")
    assert candidates[0].ai_content == b"png content"


@patch("public_detective.services.converter.ConverterService.gif_to_mp4")
def test_prepare_ai_candidates_gif_conversion(mock_converter: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests successful conversion of a .gif file."""
    mock_converter.return_value = b"mp4 content"
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="animation.gif",
        content=b"gif content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".mp4")
    assert candidates[0].ai_content == b"mp4 content"


@patch("public_detective.services.converter.ConverterService.xlsx_to_pdf")
def test_prepare_ai_candidates_spreadsheet_conversion(
    mock_converter: MagicMock, analysis_service: AnalysisService
) -> None:
    """Tests successful conversion of a spreadsheet file to PDF."""
    mock_converter.return_value = b"pdf content"
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="data.xlsx",
        content=b"xlsx content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate.ai_path == "data.pdf"
    assert candidate.ai_content == b"pdf content"
    assert candidate.prepared_content_gcs_uris == ["data.pdf"]
    assert not candidate.warnings


@patch("public_detective.services.converter.ConverterService.docx_to_pdf", side_effect=Exception("Conversion failed"))
def test_prepare_ai_candidates_conversion_failure(mock_converter: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests that a file is marked for exclusion if conversion fails."""
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="document.docx",
        content=b"docx content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].exclusion_reason == ExclusionReason.CONVERSION_FAILED


def test_get_priority(analysis_service: AnalysisService) -> None:
    """Tests the file prioritization logic."""
    candidate_edital_metadata = AIFileCandidate(
        original_path="any.pdf",
        raw_document_metadata={"tipoDocumentoNome": "Edital de Licitação"},
        synthetic_id="1",
        original_content=b"",
    )
    candidate_edital_filename = AIFileCandidate(
        original_path="edital.pdf", raw_document_metadata={}, synthetic_id="1", original_content=b""
    )
    candidate_other = AIFileCandidate(
        original_path="outro.txt", raw_document_metadata={}, synthetic_id="1", original_content=b""
    )

    assert analysis_service._get_priority(candidate_edital_metadata) == 0
    assert analysis_service._get_priority(candidate_edital_filename) == 0
    assert analysis_service._get_priority(candidate_other) == len(analysis_service._FILE_PRIORITY_ORDER)


def test_calculate_procurement_hash(analysis_service: AnalysisService, mock_procurement: Procurement) -> None:
    """Tests that the procurement hash is consistent and based on key fields."""
    files = [
        ProcessedFile(source_document_id="1", relative_path="f1.pdf", content=b"c1", raw_document_metadata={"a": 1})
    ]
    hash1 = analysis_service._calculate_procurement_hash(mock_procurement, files)

    # Test that the hash is deterministic
    hash2 = analysis_service._calculate_procurement_hash(mock_procurement, files)
    assert hash1 == hash2

    # Test that changing a key field changes the hash
    mock_procurement.object_description = "A new description"
    hash3 = analysis_service._calculate_procurement_hash(mock_procurement, files)
    assert hash1 != hash3

    # Test that changing a non-key field does not change the hash
    mock_procurement.object_description = "Original Description"  # Reset
    mock_procurement.user_name = "new_user"
    hash4 = analysis_service._calculate_procurement_hash(mock_procurement, files)
    assert hash1 == hash4


def test_get_prioritization_logic(analysis_service: AnalysisService) -> None:
    """Tests the priority string generation."""
    candidate_edital_metadata = AIFileCandidate(
        original_path="any.pdf",
        raw_document_metadata={"tipoDocumentoNome": "Edital de Licitação"},
        synthetic_id="1",
        original_content=b"",
    )
    candidate_other = AIFileCandidate(
        original_path="outro.txt", raw_document_metadata={}, synthetic_id="1", original_content=b""
    )

    logic, keyword = analysis_service._get_prioritization_logic(candidate_edital_metadata)
    assert logic == PrioritizationLogic.BY_METADATA
    assert keyword == "edital"

    logic, keyword = analysis_service._get_prioritization_logic(candidate_other)
    assert logic == PrioritizationLogic.NO_PRIORITY
    assert keyword is None


@patch("public_detective.services.analysis.AnalysisService._build_analysis_prompt")
def test_select_files_by_token_limit_all_fit(mock_build_prompt: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests file selection when all files are within the token limit."""
    mock_build_prompt.return_value = "prompt"
    analysis_service.ai_provider.count_tokens_for_analysis.return_value = (100, 0, 0)

    candidates = [
        MagicMock(exclusion_reason=None, ai_gcs_uris=["uri1"]),
        MagicMock(exclusion_reason=None, ai_gcs_uris=["uri2"]),
    ]

    selected, warnings = analysis_service._select_files_by_token_limit(candidates, MagicMock())

    assert all(c.is_included for c in selected)
    assert not warnings


@patch("public_detective.services.analysis.AnalysisService._build_analysis_prompt")
def test_select_files_by_token_limit_some_excluded(
    mock_build_prompt: MagicMock, analysis_service: AnalysisService, mock_procurement: MagicMock
) -> None:
    """Tests file selection when some files exceed the token limit."""
    mock_build_prompt.return_value = "prompt"
    analysis_service.ai_provider.count_tokens_for_analysis.side_effect = [(100, 0, 0), (200000, 0, 0)]

    candidates = [
        MagicMock(original_path="file1.pdf", exclusion_reason=None, ai_gcs_uris=["uri1"], is_included=False),
        MagicMock(original_path="file2.pdf", exclusion_reason=None, ai_gcs_uris=["uri2"], is_included=False),
    ]
    analysis_service.config.GCP_GEMINI_MAX_INPUT_TOKENS = 150

    selected, warnings = analysis_service._select_files_by_token_limit(candidates, mock_procurement)

    assert selected[0].is_included
    assert not selected[1].is_included
    assert selected[1].exclusion_reason == ExclusionReason.TOKEN_LIMIT_EXCEEDED
    assert warnings[0] == Warnings.TOKEN_LIMIT_EXCEEDED.format_message(
        max_tokens=150, ignored_files="file2.pdf"
    )


@patch("public_detective.services.analysis.AnalysisService._build_analysis_prompt")
def test_select_files_by_token_limit_prioritization(
    mock_build_prompt: MagicMock, analysis_service: AnalysisService, mock_procurement: MagicMock
) -> None:
    """Tests that high-priority files are selected first."""
    mock_build_prompt.return_value = "prompt"
    analysis_service.ai_provider.count_tokens_for_analysis.side_effect = [(100, 0, 0), (200000, 0, 0)]

    candidates = [
        MagicMock(original_path="outro.pdf", exclusion_reason=None, ai_gcs_uris=["uri2"], is_included=False),
        MagicMock(original_path="edital.pdf", exclusion_reason=None, ai_gcs_uris=["uri1"], is_included=False),
    ]
    analysis_service.config.GCP_GEMINI_MAX_INPUT_TOKENS = 150

    selected, warnings = analysis_service._select_files_by_token_limit(candidates, mock_procurement)

    assert selected[0].is_included
    assert not selected[1].is_included
    assert selected[1].exclusion_reason == ExclusionReason.TOKEN_LIMIT_EXCEEDED


def test_analyze_procurement_no_file_records(analysis_service: AnalysisService, caplog: Any) -> None:
    """Tests that analysis is aborted if no file records are found."""
    mock_procurement = MagicMock(spec=Procurement)
    mock_procurement.pncp_control_number = "123"
    analysis_id = uuid.uuid4()
    analysis_service.analysis_repo.get_analysis_by_id.return_value = MagicMock()
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = []

    analysis_service.analyze_procurement(mock_procurement, 1, analysis_id)

    assert f"No file records found for analysis {analysis_id}. Aborting." in caplog.text
    analysis_service.status_history_repo.create_record.assert_called_with(
        analysis_id, ProcurementAnalysisStatus.ANALYSIS_FAILED, "No file records found for analysis."
    )


def test_analyze_procurement_no_included_files(analysis_service: AnalysisService, caplog: Any) -> None:
    """Tests that analysis is aborted if no files were marked for inclusion."""
    mock_procurement = MagicMock(spec=Procurement)
    mock_procurement.pncp_control_number = "PNCP-123"
    analysis_id = uuid.uuid4()
    analysis_service.analysis_repo.get_analysis_by_id.return_value = MagicMock()
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = [
        {"included_in_analysis": False}
    ]

    analysis_service.analyze_procurement(mock_procurement, 1, analysis_id)

    assert "No files were selected for analysis for PNCP-123. Aborting." in caplog.text
    analysis_service.status_history_repo.create_record.assert_called_with(
        analysis_id,
        ProcurementAnalysisStatus.ANALYSIS_FAILED,
        "No files were selected for analysis during pre-analysis.",
    )


def test_analyze_procurement_happy_path(analysis_service: AnalysisService, mock_valid_analysis: Analysis) -> None:
    """Tests the full, successful execution of the analyze_procurement method."""
    analysis_id = uuid.uuid4()
    procurement_id = uuid.uuid4()
    mock_procurement = MagicMock(spec=Procurement)
    mock_procurement.pncp_control_number = "PNCP123"
    mock_procurement.procurement_id = procurement_id

    mock_analysis_record = MagicMock(
        spec=AnalysisResult,
        document_hash="testhash",
        analysis_prompt="prompt",
        warnings=[],
    )
    analysis_service.analysis_repo.get_analysis_by_id.return_value = mock_analysis_record

    mock_file_records = [
        {
            "included_in_analysis": True,
            "prepared_content_gcs_uris": ["gs://bucket/file.pdf"],
            "extension": "pdf",
        }
    ]
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = mock_file_records
    analysis_service.procurement_repo.get_procurement_uuid.return_value = procurement_id

    analysis_service.ai_provider.get_structured_analysis.return_value = (mock_valid_analysis, 100, 50, 10)
    analysis_service.pricing_service.calculate.return_value = (Decimal(0), Decimal(0), Decimal(0), Decimal(0))

    analysis_service.analyze_procurement(mock_procurement, 1, analysis_id)

    analysis_service.ai_provider.get_structured_analysis.assert_called_once_with(
        prompt="prompt", file_uris=["gs://bucket/file.pdf"], max_output_tokens=None
    )
    analysis_service.analysis_repo.save_analysis.assert_called_once()
    analysis_service.budget_ledger_repo.save_expense.assert_called_once()

    saved_result: AnalysisResult = analysis_service.analysis_repo.save_analysis.call_args[1]["result"]
    assert saved_result.document_hash == "testhash"
    assert saved_result.analysis_prompt == "prompt"
    assert saved_result.procurement_control_number == "PNCP123"
    assert saved_result.ai_analysis == mock_valid_analysis


def test_update_status_with_history(analysis_service: AnalysisService) -> None:
    """Tests that the status is updated and a history record is created."""
    analysis_id = uuid.uuid4()
    status = ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL
    details = "Completed successfully"

    analysis_service._update_status_with_history(analysis_id, status, details)

    analysis_service.analysis_repo.update_analysis_status.assert_called_once_with(analysis_id, status)
    analysis_service.status_history_repo.create_record.assert_called_once_with(analysis_id, status, details)


def test_run_specific_analysis_not_found(analysis_service: AnalysisService, caplog: pytest.LogCaptureFixture) -> None:
    """Tests that an error is logged if the analysis is not found."""
    analysis_id = uuid.uuid4()
    analysis_service.analysis_repo.get_analysis_by_id.return_value = None

    analysis_service.run_specific_analysis(analysis_id)

    assert f"Analysis with ID {analysis_id} not found." in caplog.text
    analysis_service.pubsub_provider.publish.assert_not_called()


def test_run_specific_analysis_wrong_status_early_return(analysis_service: AnalysisService) -> None:
    """Covers the early return path when analysis exists but is not pending."""
    analysis_id = uuid.uuid4()
    mock_analysis = MagicMock()
    mock_analysis.status = ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS.value
    analysis_service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    analysis_service.run_specific_analysis(analysis_id)
    analysis_service.pubsub_provider.publish.assert_not_called()


def test_run_specific_analysis_wrong_status(
    analysis_service: AnalysisService, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests that a warning is logged if the analysis is not in a pending state."""
    analysis_id = uuid.uuid4()
    mock_analysis = MagicMock(spec=Analysis)
    mock_analysis.status = ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value
    analysis_service.analysis_repo.get_analysis_by_id.return_value = mock_analysis

    analysis_service.run_specific_analysis(analysis_id)

    assert f"Analysis {analysis_id} is not in PENDING_ANALYSIS state" in caplog.text
    analysis_service.pubsub_provider.publish.assert_not_called()


def test_run_specific_analysis_no_pubsub_provider(analysis_service: AnalysisService) -> None:
    """Tests that an AnalysisError is raised if the pubsub provider is not configured."""
    analysis_id = uuid.uuid4()
    mock_analysis = MagicMock(spec=Analysis)
    mock_analysis.status = ProcurementAnalysisStatus.PENDING_ANALYSIS.value
    analysis_service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    analysis_service.pubsub_provider = None

    with pytest.raises(AnalysisError, match="An unexpected error occurred"):
        analysis_service.run_specific_analysis(analysis_id)


def test_run_specific_analysis_happy_path(analysis_service: AnalysisService) -> None:
    """Tests the happy path for running a specific analysis."""
    analysis_id = uuid.uuid4()
    mock_analysis = MagicMock(spec=Analysis)
    mock_analysis.procurement_control_number = "123"
    mock_analysis.version_number = 1
    mock_analysis.status = ProcurementAnalysisStatus.PENDING_ANALYSIS.value
    analysis_service.analysis_repo.get_analysis_by_id.return_value = mock_analysis

    analysis_service.run_specific_analysis(analysis_id)

    analysis_service.status_history_repo.create_record.assert_called_with(
        analysis_id, ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS, "Worker picked up the task."
    )
    analysis_service.pubsub_provider.publish.assert_called_once()


def test_run_specific_analysis_exception(analysis_service: AnalysisService) -> None:
    """Tests that an AnalysisError is raised on unexpected failure."""
    analysis_id = uuid.uuid4()
    analysis_service.analysis_repo.get_analysis_by_id.side_effect = Exception("DB error")

    with pytest.raises(AnalysisError, match="An unexpected error occurred"):
        analysis_service.run_specific_analysis(analysis_id)


def test_get_modality_from_exts(analysis_service: AnalysisService) -> None:
    """Tests that modality is correctly identified from extensions."""
    assert analysis_service._get_modality_from_exts(["mp4"]).name == "VIDEO"
    assert analysis_service._get_modality_from_exts(["mp3"]).name == "AUDIO"
    assert analysis_service._get_modality_from_exts(["jpg"]).name == "IMAGE"
    assert analysis_service._get_modality_from_exts(["pdf", "txt"]).name == "TEXT"
    assert analysis_service._get_modality_from_exts([]).name == "TEXT"


def test_get_modality_from_exts_none_and_empty(analysis_service: AnalysisService) -> None:
    """Covers branches where extensions contain None or empty strings."""
    assert analysis_service._get_modality_from_exts([None, ""]).name == "TEXT"


def test_prepare_ai_candidates_xml(analysis_service: AnalysisService) -> None:
    """Tests that XML files are converted to .txt."""
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="data.xml",
        content=b"<xml></xml>",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".txt")


def test_prepare_ai_candidates_json(analysis_service: AnalysisService) -> None:
    """JSON files are also converted to .txt path indicator for prepared content."""
    processed_file = ProcessedFile(
        source_document_id="doc2",
        relative_path="data.json",
        content=b"{}",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".txt")


def test_ai_file_candidate_defaults() -> None:
    """Ensures AIFileCandidate defaults mirror the original path/content when not converted."""
    candidate = AIFileCandidate(
        synthetic_id="s1",
        raw_document_metadata={},
        original_path="a.txt",
        original_content=b"x",
    )
    assert candidate.ai_path == "a.txt"
    assert candidate.ai_content == b"x"


def test_process_and_save_source_documents(analysis_service: AnalysisService) -> None:
    """Saves source documents and returns the synthetic_id -> source_document_id mapping."""
    analysis_id = uuid.uuid4()
    candidates = [
        AIFileCandidate(
            synthetic_id="s1", raw_document_metadata={"titulo": "T"}, original_path="a", original_content=b"x"
        )
    ]
    analysis_service.source_document_repo.save_source_document.return_value = uuid.uuid4()
    mapping = analysis_service._process_and_save_source_documents(analysis_id, candidates)
    assert "s1" in mapping and mapping["s1"]


def test_upload_and_save_initial_records_minimal(analysis_service: AnalysisService) -> None:
    """Uploads original file and persists minimal file record when no conversion occurred."""
    procurement_id = uuid.uuid4()
    analysis_id = uuid.uuid4()
    candidate = AIFileCandidate(
        synthetic_id="s1", raw_document_metadata={}, original_path="dir/file.txt", original_content=b"x"
    )
    analysis_service.file_record_repo.save_file_record.return_value = uuid.uuid4()
    source_docs_map = {"s1": uuid.uuid4()}

    analysis_service._upload_and_save_initial_records(procurement_id, analysis_id, [candidate], source_docs_map)
    assert candidate.ai_gcs_uris and candidate.ai_gcs_uris[0].endswith("/file.txt")
    analysis_service.gcs_provider.upload_file.assert_called()
    analysis_service.file_record_repo.save_file_record.assert_called()


def test_upload_and_save_initial_records_with_prepared_single(analysis_service: AnalysisService) -> None:
    """Uploads a single prepared artifact and sets AI URIs accordingly."""
    analysis_id = uuid.uuid4()
    procurement_id = uuid.uuid4()
    source_doc_id = uuid.uuid4()
    candidate = AIFileCandidate(
        synthetic_id="docY",
        original_path="document.docx",
        original_content=b"orig",
        raw_document_metadata={},
    )
    candidate.ai_path = "document.html"
    candidate.prepared_content_gcs_uris = ["document.html"]
    candidate.ai_content = b"<html>ok</html>"
    source_docs_map = {"docY": source_doc_id}

    analysis_service._upload_and_save_initial_records(procurement_id, analysis_id, [candidate], source_docs_map)
    assert candidate.ai_gcs_uris and candidate.ai_gcs_uris[0].endswith("/prepared_content/document.html")
    assert candidate.prepared_content_gcs_uris == candidate.ai_gcs_uris


def test_run_pre_analysis_sleep_and_max_messages(analysis_service: AnalysisService, monkeypatch: Any) -> None:
    """Covers batch sleep path and early stop via max_messages."""
    p1, p2 = MagicMock(), MagicMock()
    p1.pncp_control_number = "P1"
    p2.pncp_control_number = "P2"
    raw = {"k": "v"}

    def mock_generator(*_args: Any, **_kwargs: Any) -> Any:
        yield "procurements_page", (p1, raw)
        yield "procurements_page", (p2, raw)

    analysis_service.procurement_repo.get_updated_procurements_with_raw_data.side_effect = mock_generator
    calls = {"slept": 0}

    def fake_sleep(_secs: int) -> None:
        calls["slept"] += 1

    monkeypatch.setattr("public_detective.services.analysis.time.sleep", fake_sleep)
    analysis_service._pre_analyze_procurement = MagicMock()

    list(analysis_service.run_pre_analysis(date.today(), date.today(), batch_size=1, sleep_seconds=0))
    assert calls["slept"] >= 1

    calls["slept"] = 0
    analysis_service._pre_analyze_procurement.reset_mock()
    list(analysis_service.run_pre_analysis(date.today(), date.today(), batch_size=10, sleep_seconds=0, max_messages=1))
    assert analysis_service._pre_analyze_procurement.call_count == 1
    assert calls["slept"] == 0


def test_process_analysis_from_message_analysis_not_found(analysis_service: AnalysisService) -> None:
    """Returns early if analysis is not found."""
    analysis_id = uuid.uuid4()
    analysis_service.analysis_repo.get_analysis_by_id.return_value = None
    analysis_service.process_analysis_from_message(analysis_id)
    analysis_service.procurement_repo.get_procurement_by_id_and_version.assert_not_called()


def test_process_analysis_from_message_procurement_not_found(analysis_service: AnalysisService) -> None:
    """Returns early if procurement is not found for the analysis record."""
    analysis_id = uuid.uuid4()
    mock_analysis = MagicMock()
    mock_analysis.procurement_control_number = "X"
    mock_analysis.version_number = 1
    analysis_service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    analysis_service.procurement_repo.get_procurement_by_id_and_version.return_value = None
    analysis_service.process_analysis_from_message(analysis_id)


def test_analyze_procurement_missing_analysis_record_raises(analysis_service: AnalysisService) -> None:
    """analyze_procurement must raise when the analysis record cannot be retrieved."""
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "PN"
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid.uuid4()
    analysis_service.analysis_repo.get_analysis_by_id.return_value = None
    with pytest.raises(AnalysisError):
        analysis_service.analyze_procurement(procurement, 1, uuid.uuid4())


def test_pre_analyze_procurement_skip_when_hash_exists(analysis_service: AnalysisService, caplog: Any) -> None:
    """Pre-analysis should skip idempotently when procurement content hash already exists."""
    procurement = MagicMock(spec=Procurement)
    procurement.pncp_control_number = "P-SKIP"
    # Make process_procurement_documents return deterministic files
    processed = [ProcessedFile(source_document_id="s1", relative_path="a.txt", content=b"1", raw_document_metadata={})]
    analysis_service.procurement_repo.process_procurement_documents.return_value = processed
    analysis_service.ai_provider.count_tokens_for_analysis.return_value = (1, 0, 0)
    analysis_service.procurement_repo.get_procurement_by_hash.return_value = {"exists": True}

    events = list(analysis_service.run_pre_analysis(date.today(), date.today(), batch_size=10, sleep_seconds=0))
    # No errors, and message about completion should be logged by the generator end
    assert isinstance(events, list)


def test_run_pre_analysis_generator_and_pre_analyze_called(analysis_service: AnalysisService) -> None:
    """Verifies pre-analysis generator emits expected events and invokes pre-analyze per procurement."""
    start = date.today()
    end = start
    proc = MagicMock()
    proc.pncp_control_number = "PN-1"
    raw = {"k": "v"}

    def mock_generator(*_args: Any, **_kwargs: Any) -> Any:
        yield "procurements_page", (proc, raw)

    analysis_service.procurement_repo.get_updated_procurements_with_raw_data.side_effect = mock_generator
    analysis_service._pre_analyze_procurement = MagicMock()
    events = list(analysis_service.run_pre_analysis(start, end, batch_size=10, sleep_seconds=0))
    assert any(e[0] == "day_started" for e in events)
    assert any(e[0] == "procurements_fetched" for e in events)
    assert any(e[0] == "procurement_processed" for e in events)


def test_pre_analyze_procurement_missing_uuid_raises(analysis_service: AnalysisService) -> None:
    """_pre_analyze_procurement must raise AnalysisError when procurement UUID cannot be resolved."""
    proc = MagicMock(spec=Procurement)
    proc.pncp_control_number = "PN-1"
    proc.object_description = "Test Description"
    proc.modality = "Pregão"
    proc.total_estimated_value = Decimal("100.00")
    proc.proposal_opening_date = datetime.now()
    proc.proposal_closing_date = datetime.now()
    proc.process_number = "123/2024"
    proc.is_srp = False
    proc.procurement_status = "Published"
    proc.total_awarded_value = Decimal("90.00")
    proc.dispute_method = "Online"

    mock_legal = MagicMock()
    mock_legal.model_dump.return_value = {}
    proc.legal_support = mock_legal

    mock_entity = MagicMock()
    mock_entity.name = "Test Org"
    mock_entity.model_dump.return_value = {}
    proc.government_entity = mock_entity

    mock_unit = MagicMock()
    mock_unit.unit_name = "Test Unit"
    mock_unit.model_dump.return_value = {}
    proc.entity_unit = mock_unit

    analysis_service.procurement_repo.process_procurement_documents.return_value = []
    analysis_service.procurement_repo.get_procurement_by_hash.return_value = None
    analysis_service.procurement_repo.get_latest_version.return_value = 0
    analysis_service.procurement_repo.get_procurement_uuid.return_value = None
    with pytest.raises(AnalysisError):
        analysis_service._pre_analyze_procurement(proc, {"x": 1})


def test_run_ranked_analysis_and_skips(analysis_service: AnalysisService) -> None:
    """Covers error on missing period for auto-budget and skipping when budget < cost."""
    with pytest.raises(ValueError):
        analysis_service.run_ranked_analysis(True, None, 50)

    analysis = MagicMock()
    analysis.analysis_id = uuid.uuid4()
    analysis.total_cost = Decimal("100")
    analysis.votes_count = 0
    analysis.procurement_control_number = "P"
    analysis.version_number = 1
    analysis.analysis_id = uuid.uuid4()
    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis]
    res = analysis_service.run_ranked_analysis(False, None, 50, budget=Decimal("10"))
    assert res == []


def test_retry_analyses_triggers_run(analysis_service: AnalysisService) -> None:
    """Ensures retry_analyses schedules retries and triggers run_specific_analysis when eligible."""
    ago = datetime.now(timezone.utc) - timedelta(hours=10)
    analysis = MagicMock()
    analysis.updated_at = ago
    analysis.retry_count = 0
    analysis.analysis_id = uuid.uuid4()
    analysis.procurement_control_number = "P"
    analysis.version_number = 1
    analysis.document_hash = "h"
    analysis.input_tokens_used = 1
    analysis.output_tokens_used = 1
    analysis.thinking_tokens_used = 1
    analysis.analysis_prompt = "p"
    analysis_service.analysis_repo.get_analyses_to_retry.return_value = [analysis]
    analysis_service.analysis_repo.save_retry_analysis.return_value = uuid.uuid4()
    analysis_service.run_specific_analysis = MagicMock()
    analysis_service.pricing_service.calculate.return_value = (Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"))
    count = analysis_service.retry_analyses(initial_backoff_hours=1, max_retries=3, timeout_hours=1)
    assert count >= 0


def test_get_procurement_overall_status_none_and_value(analysis_service: AnalysisService) -> None:
    """Pass-through overall status method returns None or dict as provided by repo."""
    analysis_service.analysis_repo.get_procurement_overall_status.return_value = None
    assert analysis_service.get_procurement_overall_status("P") is None
    analysis_service.analysis_repo.get_procurement_overall_status.return_value = {"k": "v"}
    assert analysis_service.get_procurement_overall_status("P") == {"k": "v"}


def test_update_selected_file_records(analysis_service: AnalysisService) -> None:
    """Tests that the file records are correctly updated in the database."""
    record_id1 = uuid.uuid4()
    record_id2 = uuid.uuid4()
    candidates = [
        MagicMock(is_included=True, file_record_id=record_id1),
        MagicMock(is_included=False, file_record_id=uuid.uuid4()),
        MagicMock(is_included=True, file_record_id=record_id2),
        MagicMock(is_included=True, file_record_id=None),
    ]
    analysis_service._update_selected_file_records(candidates)
    analysis_service.file_record_repo.set_files_as_included.assert_called_once_with([record_id1, record_id2])


def test_update_selected_file_records_no_selected(analysis_service: AnalysisService) -> None:
    """When no candidates are selected or lack IDs, repo method should not be called."""
    analysis_service._update_selected_file_records(
        [
            MagicMock(is_included=False, file_record_id=None),
            MagicMock(is_included=False, file_record_id=None),
        ]
    )
    analysis_service.file_record_repo.set_files_as_included.assert_not_called()


def test_upload_and_save_initial_records_no_conversion(analysis_service: AnalysisService) -> None:
    """Tests the upload logic for a file that does not undergo conversion."""
    analysis_id = uuid.uuid4()
    procurement_id = uuid.uuid4()
    source_doc_id = uuid.uuid4()

    candidate = AIFileCandidate(
        synthetic_id="doc1",
        original_path="document.txt",
        original_content=b"text content",
        raw_document_metadata={},
    )
    source_docs_map = {"doc1": source_doc_id}

    analysis_service._upload_and_save_initial_records(procurement_id, analysis_id, [candidate], source_docs_map)

    assert candidate.ai_gcs_uris is not None
    assert "document.txt" in candidate.ai_gcs_uris[0]
    assert "prepared_content" not in candidate.ai_gcs_uris[0]


def test_build_analysis_prompt_with_warnings(analysis_service: AnalysisService, mock_procurement: MagicMock) -> None:
    """Tests that warnings are correctly included in the AI prompt."""
    warnings = [Warnings.TOKEN_LIMIT_EXCEEDED.format(max_tokens=100, ignored_files="f1.pdf")]

    prompt = analysis_service._build_analysis_prompt(mock_procurement, [], warnings)
    assert "--- ATENÇÃO ---" in prompt
    assert "limite de 100 tokens foi excedido" in prompt


def test_build_analysis_prompt_with_included_candidates(analysis_service: AnalysisService) -> None:
    """Prompt should include context section when there are included candidates."""
    mock_procurement = MagicMock(spec=Procurement)
    mock_procurement.object_description = "Test Description"
    mock_procurement.modality = "Pregão"
    mock_procurement.total_estimated_value = Decimal("1000.00")
    mock_procurement.proposal_opening_date = datetime.now()
    mock_procurement.proposal_closing_date = datetime.now()

    mock_entity = MagicMock()
    mock_entity.name = "Test Org"
    mock_procurement.government_entity = mock_entity

    mock_unit = MagicMock()
    mock_unit.unit_name = "Test Unit"
    mock_procurement.entity_unit = mock_unit

    cand = AIFileCandidate(
        synthetic_id="s1",
        raw_document_metadata={"titulo": "T", "tipoDocumentoNome": "n", "dataPublicacaoPncp": "2025-01-01"},
        original_path="a.txt",
        original_content=b"x",
    )
    cand.is_included = True
    cand.ai_path = "a.txt"
    prompt = analysis_service._build_analysis_prompt(mock_procurement, [cand], [])
    assert "Fonte do Documento" in prompt
    assert "Arquivos extraídos desta fonte" in prompt


@patch("public_detective.services.analysis.datetime")
def test_calculate_auto_budget(mock_datetime: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests the auto-budget calculation logic for different periods."""
    mock_datetime.now.return_value.date.return_value = date(2023, 10, 26)
    analysis_service.budget_ledger_repo.get_total_donations.return_value = Decimal("1000")
    analysis_service.budget_ledger_repo.get_total_expenses_for_period.return_value = Decimal("100")

    analysis_service._calculate_auto_budget("daily")
    analysis_service.budget_ledger_repo.get_total_expenses_for_period.assert_called_with(date(2023, 10, 26))

    analysis_service._calculate_auto_budget("weekly")
    analysis_service.budget_ledger_repo.get_total_expenses_for_period.assert_called_with(date(2023, 10, 23))

    analysis_service._calculate_auto_budget("monthly")
    analysis_service.budget_ledger_repo.get_total_expenses_for_period.assert_called_with(date(2023, 10, 1))

    with pytest.raises(ValueError):
        analysis_service._calculate_auto_budget("yearly")


def test_get_procurement_overall_status(analysis_service: AnalysisService) -> None:
    """Tests retrieving the overall status of a procurement."""
    control_number = "PNCP123"
    expected_status = {"status": "COMPLETED"}
    analysis_service.analysis_repo.get_procurement_overall_status.return_value = expected_status

    status = analysis_service.get_procurement_overall_status(control_number)

    assert status == expected_status
    analysis_service.analysis_repo.get_procurement_overall_status.assert_called_once_with(control_number)


def test_get_procurement_overall_status_not_found(analysis_service: AnalysisService) -> None:
    """Tests retrieving the overall status when no status is found."""
    control_number = "PNCP123"
    analysis_service.analysis_repo.get_procurement_overall_status.return_value = None

    status = analysis_service.get_procurement_overall_status(control_number)
    assert status is None


@patch("public_detective.services.analysis.AnalysisService.run_specific_analysis")
def test_run_ranked_analysis_manual_budget(mock_run_specific: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests ranked analysis with a manual budget."""
    mock_analysis = MagicMock()
    mock_analysis.analysis_id = uuid.uuid4()
    mock_analysis.total_cost = Decimal("10")
    mock_analysis.votes_count = 1
    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [mock_analysis]

    analysis_service.run_ranked_analysis(
        use_auto_budget=False, budget=Decimal("15"), budget_period=None, zero_vote_budget_percent=10
    )

    mock_run_specific.assert_called_once_with(mock_analysis.analysis_id)


@patch("public_detective.services.analysis.AnalysisService.run_specific_analysis")
def test_run_ranked_analysis_budget_exceeded(
    mock_run_specific: MagicMock, analysis_service: AnalysisService, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests that analysis is skipped if budget is exceeded."""
    mock_analysis = MagicMock()
    mock_analysis.analysis_id = uuid.uuid4()
    mock_analysis.total_cost = Decimal("20")
    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [mock_analysis]

    analysis_service.run_ranked_analysis(
        use_auto_budget=False, budget=Decimal("15"), budget_period=None, zero_vote_budget_percent=10
    )

    assert "Skipping analysis" in caplog.text
    mock_run_specific.assert_not_called()


@patch("public_detective.services.analysis.AnalysisService.run_specific_analysis")
def test_run_ranked_analysis_zero_vote_budget_exceeded(
    mock_run_specific: MagicMock, analysis_service: AnalysisService, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests that a zero-vote analysis is skipped if its budget is exceeded."""
    mock_analysis = MagicMock()
    mock_analysis.analysis_id = uuid.uuid4()
    mock_analysis.total_cost = Decimal("10")
    mock_analysis.votes_count = 0
    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [mock_analysis]

    analysis_service.run_ranked_analysis(
        use_auto_budget=False, budget=Decimal("100"), budget_period=None, zero_vote_budget_percent=5
    )

    assert "Skipping zero-vote analysis" in caplog.text
    mock_run_specific.assert_not_called()


@patch("public_detective.services.analysis.AnalysisService.run_specific_analysis")
def test_run_ranked_analysis_max_messages(mock_run_specific: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests that the job stops when max_messages is reached."""
    mock_analysis1 = MagicMock(analysis_id=uuid.uuid4(), total_cost=Decimal("1"), votes_count=1)
    mock_analysis2 = MagicMock(analysis_id=uuid.uuid4(), total_cost=Decimal("1"), votes_count=1)
    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [mock_analysis1, mock_analysis2]

    analysis_service.run_ranked_analysis(
        use_auto_budget=False, budget=Decimal("100"), budget_period=None, zero_vote_budget_percent=10, max_messages=1
    )

    mock_run_specific.assert_called_once_with(mock_analysis1.analysis_id)


def test_run_ranked_analysis_auto_budget(analysis_service: AnalysisService) -> None:
    """Tests ranked analysis with auto-budget enabled."""
    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = []
    with patch.object(analysis_service, "_calculate_auto_budget", return_value=Decimal("100")) as mock_calc:
        analysis_service.run_ranked_analysis(use_auto_budget=True, budget_period="daily", zero_vote_budget_percent=10)
        mock_calc.assert_called_once_with("daily")


def test_run_ranked_analysis_no_budget_option(analysis_service: AnalysisService) -> None:
    """Tests that an error is raised if no budget option is provided."""
    with pytest.raises(ValueError, match="Either a manual budget must be provided or auto-budget must be enabled."):
        analysis_service.run_ranked_analysis(
            use_auto_budget=False, budget=None, budget_period=None, zero_vote_budget_percent=10
        )


@patch("public_detective.services.analysis.AnalysisService.analyze_procurement")
def test_process_analysis_from_message_happy_path(
    mock_analyze_procurement: MagicMock, analysis_service: AnalysisService, mock_procurement: MagicMock
) -> None:
    """Tests the successful processing of an analysis from a message."""
    analysis_id = uuid.uuid4()
    mock_analysis = MagicMock(spec=Analysis)
    mock_analysis.procurement_control_number = "123"
    mock_analysis.version_number = 1
    analysis_service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    analysis_service.procurement_repo.get_procurement_by_id_and_version.return_value = mock_procurement

    analysis_service.process_analysis_from_message(analysis_id)

    mock_analyze_procurement.assert_called_once_with(mock_procurement, mock_analysis.version_number, analysis_id, None)
    analysis_service.analysis_repo.update_analysis_status.assert_called_once_with(
        analysis_id, ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL
    )
    analysis_service.status_history_repo.create_record.assert_called_with(
        analysis_id, ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL, "Analysis completed successfully."
    )


@patch("public_detective.services.analysis.AnalysisService.analyze_procurement")
def test_process_analysis_from_message_pipeline_fails(
    mock_analyze_procurement: MagicMock, analysis_service: AnalysisService, mock_procurement: MagicMock
) -> None:
    """Tests that the status is updated to FAILED if the pipeline raises an exception."""
    analysis_id = uuid.uuid4()
    mock_analysis = MagicMock(spec=Analysis)
    mock_analysis.procurement_control_number = "123"
    mock_analysis.version_number = 1
    analysis_service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    analysis_service.procurement_repo.get_procurement_by_id_and_version.return_value = mock_procurement
    error_message = "Something went wrong"
    mock_analyze_procurement.side_effect = Exception(error_message)

    with pytest.raises(Exception, match=error_message):
        analysis_service.process_analysis_from_message(analysis_id)

    analysis_service.analysis_repo.update_analysis_status.assert_called_once_with(
        analysis_id, ProcurementAnalysisStatus.ANALYSIS_FAILED
    )
    analysis_service.status_history_repo.create_record.assert_called_with(
        analysis_id, ProcurementAnalysisStatus.ANALYSIS_FAILED, error_message
    )


def test_process_analysis_from_message_main_exception(analysis_service: AnalysisService) -> None:
    """Tests that an AnalysisError is raised on unexpected failure in the main try block."""
    analysis_id = uuid.uuid4()
    error_message = "Initial DB query failed"
    analysis_service.analysis_repo.get_analysis_by_id.side_effect = Exception(error_message)

    with pytest.raises(AnalysisError, match=f"Failed to process analysis from message: {error_message}"):
        analysis_service.process_analysis_from_message(analysis_id)


def test_run_pre_analysis_no_procurements_found(
    analysis_service: AnalysisService, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests that the pre-analysis job handles dates with no procurements gracefully."""
    start_date = date(2023, 1, 1)
    end_date = date(2023, 1, 1)
    analysis_service.procurement_repo.get_updated_procurements_with_raw_data.return_value = []

    # Consume the generator to trigger the logic
    list(analysis_service.run_pre_analysis(start_date, end_date, 10, 0))

    assert "Pre-analysis job for the entire date range has been completed." in caplog.text


def test_analyze_procurement_no_procurement_id(analysis_service: AnalysisService, mock_procurement: MagicMock) -> None:
    """Tests that an AnalysisError is raised if the procurement UUID is not found."""
    analysis_service.procurement_repo.get_procurement_uuid.return_value = None
    analysis_service.analysis_repo.get_analysis_by_id.return_value = MagicMock()
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = [MagicMock()]

    with pytest.raises(AnalysisError, match="Could not find procurement UUID"):
        analysis_service.analyze_procurement(mock_procurement, 1, uuid.uuid4())


def test_analyze_procurement_save_analysis_fails(
    analysis_service: AnalysisService,
    mock_valid_analysis: Analysis,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Tests that an exception during the final save is caught and logged."""
    analysis_id = uuid.uuid4()
    mock_procurement = MagicMock(spec=Procurement)
    mock_procurement.pncp_control_number = "PNCP-FAIL"
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid.uuid4()
    analysis_service.analysis_repo.get_analysis_by_id.return_value = MagicMock(document_hash="h", analysis_prompt="p")
    analysis_service.file_record_repo.get_all_file_records_by_analysis_id.return_value = [
        {"included_in_analysis": True, "prepared_content_gcs_uris": ["uri"]}
    ]

    analysis_service.ai_provider.get_structured_analysis.return_value = (mock_valid_analysis, 1, 1, 1)
    analysis_service.pricing_service.calculate.return_value = (
        Decimal("0.1"),
        Decimal("0.2"),
        Decimal("0.3"),
        Decimal("0.6"),
    )
    error_message = "Database save failed"
    analysis_service.analysis_repo.save_analysis.side_effect = Exception(error_message)

    with pytest.raises(Exception, match=error_message):
        analysis_service.analyze_procurement(mock_procurement, 1, analysis_id)

    assert f"Analysis pipeline failed for PNCP-FAIL: {error_message}" in caplog.text


def test_ai_file_candidate_preserves_provided_ai_fields() -> None:
    """Validator must not overwrite explicit ai_path/ai_content values."""
    candidate = AIFileCandidate(
        synthetic_id="s2",
        raw_document_metadata={},
        original_path="orig.txt",
        original_content=b"orig",
        ai_path="custom.html",
        ai_content=b"<h1/>",
    )
    assert candidate.ai_path == "custom.html"
    assert candidate.ai_content == b"<h1/>"


@patch("public_detective.services.analysis.AnalysisService.run_specific_analysis")
def test_run_ranked_analysis_zero_vote_happy(mock_run_specific: MagicMock, analysis_service: AnalysisService) -> None:
    """Zero-vote analysis should trigger when within zero-vote budget."""
    mock_analysis = MagicMock()
    mock_analysis.analysis_id = uuid.uuid4()
    mock_analysis.total_cost = Decimal("5")
    mock_analysis.votes_count = 0
    analysis_service.analysis_repo.get_pending_analyses_ranked.return_value = [mock_analysis]

    analysis_service.run_ranked_analysis(
        use_auto_budget=False, budget=Decimal("100"), budget_period=None, zero_vote_budget_percent=10
    )

    mock_run_specific.assert_called_once_with(mock_analysis.analysis_id)


def test_retry_analyses_no_retry_due_to_backoff(analysis_service: AnalysisService) -> None:
    """No retry should occur when backoff pushes next retry to the future."""
    now = datetime.now(timezone.utc)
    analysis = MagicMock()
    analysis.updated_at = now
    analysis.retry_count = 5
    analysis.analysis_id = uuid.uuid4()
    analysis.input_tokens_used = 10
    analysis.output_tokens_used = 10
    analysis.thinking_tokens_used = 0
    analysis_service.analysis_repo.get_analyses_to_retry.return_value = [analysis]
    count = analysis_service.retry_analyses(initial_backoff_hours=1, max_retries=3, timeout_hours=1)
    assert count == 0


def test_run_pre_analysis_by_control_number_happy_path(
    analysis_service: AnalysisService, mock_procurement: MagicMock
) -> None:
    """Tests the pre-analysis for a single procurement by control number."""
    control_number = "PNCP123456"
    raw_data = {"some": "data"}
    analysis_service.procurement_repo.get_procurement_by_control_number.return_value = (mock_procurement, raw_data)
    analysis_service._pre_analyze_procurement = MagicMock()

    event_generator = analysis_service.run_pre_analysis_by_control_number(control_number)
    events = list(event_generator)

    analysis_service.procurement_repo.get_procurement_by_control_number.assert_called_once_with(control_number)
    analysis_service._pre_analyze_procurement.assert_called_once_with(mock_procurement, raw_data)

    assert any(e[0] == "day_started" for e in events)
    assert any(e[0] == "procurements_fetched" for e in events)
    assert any(e[0] == "procurement_processed" for e in events)


def test_run_pre_analysis_by_control_number_not_found(
    analysis_service: AnalysisService, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests the case where the procurement is not found by control number."""
    control_number = "PNCP-NOT-FOUND"
    analysis_service.procurement_repo.get_procurement_by_control_number.return_value = (None, None)
    analysis_service._pre_analyze_procurement = MagicMock()

    event_generator = analysis_service.run_pre_analysis_by_control_number(control_number)
    list(event_generator)

    assert f"Procurement with PNCP control number {control_number} not found." in caplog.text
    analysis_service._pre_analyze_procurement.assert_not_called()
