"""Unit tests for the AnalysisService."""

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from public_detective.constants.analysis_feedback import Warnings
from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.analyses import Analysis, AnalysisResult
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

    # Mock nested attributes
    procurement.legal_support = MagicMock()
    procurement.legal_support.model_dump.return_value = {"codigo": 1, "nome": "Lei"}

    procurement.government_entity = MagicMock()
    procurement.government_entity.model_dump.return_value = {"cnpj": "001", "razaoSocial": "Org"}
    procurement.government_entity.name = "Org"

    procurement.entity_unit = MagicMock()
    procurement.entity_unit.model_dump.return_value = {"codigoUnidade": "U01", "nomeUnidade": "Unit"}
    procurement.entity_unit.unit_name = "Unit"

    procurement.is_srp = False
    procurement.modality = 1
    procurement.pncp_control_number = "PNCP123"
    procurement.procurement_status = 1
    procurement.total_estimated_value = Decimal("1000.00")
    procurement.total_awarded_value = Decimal("950.00")
    procurement.proposal_opening_date = None
    procurement.proposal_closing_date = None
    procurement.dispute_method = 1
    procurement.user_name = "original_user"
    return procurement


@pytest.fixture
def mock_valid_analysis() -> Analysis:
    """Provides a valid Analysis object for mocking."""
    return Analysis(
        direcionamentoLicitacao=[],
        restricaoCompetitividade=[],
        sobrepreco=[],
        resumoLicitacao="Resumo da licitação.",
        resumoAnalise="Resumo da análise.",
        notaRisco=5,
        justificativaNotaRisco="Justificativa da nota.",
        palavrasChaveSeo=["teste", "cobertura"],
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
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="document.unsupported",
        content=b"some content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].exclusion_reason is not None
    assert "Extensão de arquivo não suportada" in candidates[0].exclusion_reason


@patch("public_detective.services.converter.ConverterService.docx_to_html")
def test_prepare_ai_candidates_docx_conversion(mock_converter: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests successful conversion of a .docx file."""
    mock_converter.return_value = "<html><body>test</body></html>"
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="document.docx",
        content=b"docx content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".html")
    assert candidates[0].ai_content == b"<html><body>test</body></html>"
    assert candidates[0].exclusion_reason is None


@patch("public_detective.services.converter.ConverterService.rtf_to_text")
def test_prepare_ai_candidates_rtf_conversion(mock_converter: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests successful conversion of an .rtf file."""
    mock_converter.return_value = "rtf text"
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="document.rtf",
        content=b"rtf content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".txt")
    assert candidates[0].ai_content == b"rtf text"


@patch("public_detective.services.converter.ConverterService.doc_to_text")
def test_prepare_ai_candidates_doc_conversion(mock_converter: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests successful conversion of a .doc file."""
    mock_converter.return_value = "doc text"
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="document.doc",
        content=b"doc content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert candidates[0].ai_path.endswith(".txt")
    assert candidates[0].ai_content == b"doc text"


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


@patch("public_detective.services.converter.ConverterService.spreadsheet_to_csvs")
def test_prepare_ai_candidates_spreadsheet_conversion(
    mock_converter: MagicMock, analysis_service: AnalysisService
) -> None:
    """Tests successful conversion of a spreadsheet file."""
    mock_converter.return_value = [("sheet1", b"csv1"), ("sheet2", b"csv2")]
    processed_file = ProcessedFile(
        source_document_id="doc1",
        relative_path="data.xlsx",
        content=b"xlsx content",
        raw_document_metadata={},
    )
    candidates = analysis_service._prepare_ai_candidates([processed_file])
    assert len(candidates) == 1
    assert "data_sheet1.csv" in candidates[0].prepared_content_gcs_uris
    assert "data_sheet2.csv" in candidates[0].prepared_content_gcs_uris
    assert candidates[0].ai_content == [b"csv1", b"csv2"]


@patch("public_detective.services.converter.ConverterService.docx_to_html", side_effect=Exception("Conversion failed"))
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
    assert "Falha ao converter o arquivo" in candidates[0].exclusion_reason


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


def test_get_priority_as_string(analysis_service: AnalysisService) -> None:
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

    assert "edital" in analysis_service._get_priority_as_string(candidate_edital_metadata)
    assert "metadados" in analysis_service._get_priority_as_string(candidate_edital_metadata)
    assert "Sem priorização." in analysis_service._get_priority_as_string(candidate_other)


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
    assert "limite de 150 tokens foi excedido" in selected[1].exclusion_reason
    assert "Arquivos ignorados" in warnings[0]


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
    assert "limite de 150 tokens foi excedido" in selected[1].exclusion_reason


def test_analyze_procurement_no_files_found(
    analysis_service: AnalysisService, caplog: Any, mock_procurement: MagicMock
) -> None:
    """Tests that the analysis is aborted if no files are found for the procurement."""
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid.uuid4()
    analysis_service.procurement_repo.process_procurement_documents.return_value = []

    analysis_service.analyze_procurement(mock_procurement, 1, uuid.uuid4())

    assert "No files found for" in caplog.text


def test_analyze_procurement_no_supported_files(
    analysis_service: AnalysisService, caplog: Any, mock_procurement: MagicMock
) -> None:
    """Tests that the analysis is aborted if no supported files are left after filtering."""
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid.uuid4()
    analysis_service.procurement_repo.process_procurement_documents.return_value = [MagicMock()]
    analysis_service.source_document_repo.save_source_document.return_value = uuid.uuid4()
    analysis_service._prepare_ai_candidates = MagicMock(
        return_value=[
            MagicMock(
                spec=AIFileCandidate,
                synthetic_id="doc1",
                raw_document_metadata={},
                original_path="test.unsupported",
                original_content=b"test",
                is_included=False,
                exclusion_reason="Unsupported",
                ai_gcs_uris=[],
                prepared_content_gcs_uris=None,
                ai_content=b"test",
                ai_path="test.unsupported",
            )
        ]
    )
    analysis_service._select_files_by_token_limit = MagicMock(return_value=([], []))
    analysis_service.analyze_procurement(mock_procurement, 1, uuid.uuid4())
    assert f"No supported files left after filtering for {mock_procurement.pncp_control_number}" in caplog.text


@patch("public_detective.services.analysis.AnalysisService._get_modality")
@patch("public_detective.services.analysis.AnalysisService._calculate_hash")
def test_analyze_procurement_happy_path(
    mock_hash: MagicMock,
    mock_get_modality: MagicMock,
    analysis_service: AnalysisService,
    mock_valid_analysis: Analysis,
    mock_procurement: MagicMock,
) -> None:
    """Tests the full, successful execution of the analyze_procurement method."""
    mock_hash.return_value = "testhash"
    mock_get_modality.return_value = "TEXT"

    analysis_id = uuid.uuid4()
    procurement_id = uuid.uuid4()

    analysis_service.procurement_repo.get_procurement_uuid.return_value = procurement_id
    analysis_service.procurement_repo.process_procurement_documents.return_value = [MagicMock()]

    mock_candidate = MagicMock(
        spec=AIFileCandidate,
        is_included=True,
        ai_gcs_uris=["gs://bucket/file.pdf"],
        ai_path="file.pdf",
        ai_content=b"content",
    )
    analysis_service._prepare_ai_candidates = MagicMock(return_value=[mock_candidate])
    analysis_service._select_files_by_token_limit = MagicMock(return_value=([mock_candidate], []))
    analysis_service._process_and_save_source_documents = MagicMock(return_value={})
    analysis_service._upload_and_save_initial_records = MagicMock()
    analysis_service._update_selected_file_records = MagicMock()
    analysis_service._build_analysis_prompt = MagicMock(return_value="prompt")

    analysis_service.ai_provider.get_structured_analysis.return_value = (mock_valid_analysis, 100, 50, 10)
    analysis_service.pricing_service.calculate.return_value = (0, 0, 0, 0)

    analysis_service.analyze_procurement(mock_procurement, 1, analysis_id)

    analysis_service.ai_provider.get_structured_analysis.assert_called_once()
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


def test_get_modality_image(analysis_service: AnalysisService) -> None:
    """Tests that image modality is correctly identified."""
    candidates = [
        AIFileCandidate(original_path="test.jpg", original_content=b"", synthetic_id="1", raw_document_metadata={})
    ]
    assert analysis_service._get_modality(candidates).name == "IMAGE"


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

    with pytest.raises(AnalysisError, match="Could not find procurement UUID"):
        analysis_service.analyze_procurement(mock_procurement, 1, uuid.uuid4())


def test_analyze_procurement_no_files_left_for_ai(
    analysis_service: AnalysisService, caplog: pytest.LogCaptureFixture, mock_procurement: MagicMock
) -> None:
    """Tests that an error is logged if no files are left after token filtering."""
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid.uuid4()
    analysis_service.procurement_repo.process_procurement_documents.return_value = [MagicMock()]

    # Provide a more realistic mock to avoid ValidationError
    mock_prepared_candidate = AIFileCandidate(
        synthetic_id="doc1",
        raw_document_metadata={"titulo": "Test Doc"},
        original_path="test.pdf",
        original_content=b"content",
    )
    analysis_service._prepare_ai_candidates = MagicMock(return_value=[mock_prepared_candidate])
    analysis_service.source_document_repo.save_source_document.return_value = uuid.uuid4()

    # Mock the selection process to return a candidate that is not included
    mock_selected_candidate = MagicMock(is_included=False)
    analysis_service._select_files_by_token_limit = MagicMock(return_value=([mock_selected_candidate], []))

    analysis_service.analyze_procurement(mock_procurement, 1, uuid.uuid4())

    assert "No supported files left after filtering" in caplog.text
    analysis_service.ai_provider.get_structured_analysis.assert_not_called()


def test_analyze_procurement_save_analysis_fails(
    analysis_service: AnalysisService,
    mock_valid_analysis: Analysis,
    caplog: pytest.LogCaptureFixture,
    mock_procurement: MagicMock,
) -> None:
    """Tests that an exception during the final save is caught and logged."""
    analysis_id = uuid.uuid4()
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid.uuid4()
    analysis_service.procurement_repo.process_procurement_documents.return_value = [MagicMock()]
    analysis_service.source_document_repo.save_source_document.return_value = uuid.uuid4()

    mock_candidate = AIFileCandidate(
        synthetic_id="doc1",
        raw_document_metadata={"titulo": "Test Doc"},
        original_path="test.pdf",
        original_content=b"content",
        is_included=True,
        ai_gcs_uris=["uri1"],
        ai_path="p",
        ai_content=b"c",
    )
    analysis_service._prepare_ai_candidates = MagicMock(return_value=[mock_candidate])
    analysis_service._select_files_by_token_limit = MagicMock(return_value=([mock_candidate], []))
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

    assert f"Analysis pipeline failed for {mock_procurement.pncp_control_number}: {error_message}" in caplog.text


def test_get_modality_video(analysis_service: AnalysisService) -> None:
    """Tests that video modality is correctly identified."""
    candidates = [
        AIFileCandidate(original_path="test.mp4", original_content=b"", synthetic_id="1", raw_document_metadata={})
    ]
    assert analysis_service._get_modality(candidates).name == "VIDEO"


def test_get_modality_audio(analysis_service: AnalysisService) -> None:
    """Tests that audio modality is correctly identified."""
    candidates = [
        AIFileCandidate(original_path="test.mp3", original_content=b"", synthetic_id="1", raw_document_metadata={})
    ]
    assert analysis_service._get_modality(candidates).name == "AUDIO"


def test_calculate_procurement_hash_no_files(analysis_service: AnalysisService, mock_procurement: Procurement) -> None:
    """Tests that the procurement hash is consistent and based on key fields."""
    hash1 = analysis_service._calculate_procurement_hash(mock_procurement, [])
    hash2 = analysis_service._calculate_procurement_hash(mock_procurement, [])
    assert hash1 == hash2

    mock_procurement.object_description = "A new description"
    hash3 = analysis_service._calculate_procurement_hash(mock_procurement, [])
    assert hash1 != hash3


def test_calculate_procurement_hash_with_files(
    analysis_service: AnalysisService, mock_procurement: Procurement
) -> None:
    """Tests that the procurement hash is consistent and based on key fields."""
    files = [
        ProcessedFile(source_document_id="1", relative_path="f1.pdf", content=b"c1", raw_document_metadata={"a": 1})
    ]
    hash1 = analysis_service._calculate_procurement_hash(mock_procurement, files)

    files.append(
        ProcessedFile(source_document_id="2", relative_path="f2.pdf", content=b"c2", raw_document_metadata={"b": 2})
    )
    hash2 = analysis_service._calculate_procurement_hash(mock_procurement, files)
    assert hash1 != hash2


def test_prepare_ai_candidates_xml_json(analysis_service: AnalysisService) -> None:
    """Tests that XML and JSON files are converted to .txt."""
    processed_files = [
        ProcessedFile(
            source_document_id="doc1",
            relative_path="data.xml",
            content=b"<xml></xml>",
            raw_document_metadata={},
        ),
        ProcessedFile(
            source_document_id="doc2",
            relative_path="data.json",
            content=b"{}",
            raw_document_metadata={},
        ),
    ]
    candidates = analysis_service._prepare_ai_candidates(processed_files)
    assert len(candidates) == 2
    assert candidates[0].ai_path.endswith(".txt")
    assert candidates[1].ai_path.endswith(".txt")


def test_upload_and_save_initial_records_no_prepared_content(
    analysis_service: AnalysisService,
) -> None:
    """Tests the upload logic for a file that does not undergo conversion."""
    analysis_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    procurement_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    source_doc_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"

    candidate = AIFileCandidate(
        synthetic_id="doc1",
        original_path="document.txt",
        original_content=b"text content",
        raw_document_metadata={},
        prepared_content_gcs_uris=None,
    )
    source_docs_map = {"doc1": source_doc_id}

    analysis_service._upload_and_save_initial_records(procurement_id, analysis_id, [candidate], source_docs_map)

    assert candidate.ai_gcs_uris is not None
    assert "document.txt" in candidate.ai_gcs_uris[0]
    assert "prepared_content" not in candidate.ai_gcs_uris[0]


def test_upload_and_save_initial_records_with_gcs_prefix(
    analysis_service: AnalysisService,
) -> None:
    """Tests the upload logic for a file that does not undergo conversion."""
    analysis_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    procurement_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    source_doc_id = "f47ac10b-58cc-4372-a567-0e02b2c3d479"
    analysis_service.gcs_path_prefix = "test-prefix"

    candidate = AIFileCandidate(
        synthetic_id="doc1",
        original_path="document.txt",
        original_content=b"text content",
        raw_document_metadata={},
        prepared_content_gcs_uris=None,
    )
    source_docs_map = {"doc1": source_doc_id}

    analysis_service._upload_and_save_initial_records(procurement_id, analysis_id, [candidate], source_docs_map)

    assert candidate.ai_gcs_uris is not None
    assert "test-prefix" in candidate.ai_gcs_uris[0]


@patch("public_detective.services.analysis.datetime")
def test_retry_analyses(mock_datetime: MagicMock, analysis_service: AnalysisService) -> None:
    """Tests the retry logic for failed or stale analyses."""
    now = datetime(2023, 1, 10, 12, 0, 0, tzinfo=timezone.utc)
    mock_datetime.now.return_value = now

    mock_analysis_to_retry = MagicMock()
    mock_analysis_to_retry.analysis_id = uuid.uuid4()
    mock_analysis_to_retry.retry_count = 0
    mock_analysis_to_retry.updated_at = datetime(2023, 1, 10, 0, 0, 0)

    analysis_service.analysis_repo.get_analyses_to_retry.return_value = [mock_analysis_to_retry]
    analysis_service.run_specific_analysis = MagicMock()
    analysis_service.pricing_service.calculate.return_value = (
        Decimal("0.1"),
        Decimal("0.2"),
        Decimal("0.3"),
        Decimal("0.6"),
    )

    retried_count = analysis_service.retry_analyses(initial_backoff_hours=6, max_retries=3, timeout_hours=24)

    assert retried_count == 1
    analysis_service.analysis_repo.save_retry_analysis.assert_called_once()
    analysis_service.run_specific_analysis.assert_called_once()


def test_select_files_by_token_limit_multiple_exclusion_reasons(
    analysis_service: AnalysisService, mock_procurement: MagicMock
) -> None:
    """Tests that warnings are generated correctly for multiple exclusion reasons."""
    analysis_service.ai_provider.count_tokens_for_analysis.return_value = (100, 0, 0)

    candidates = [
        MagicMock(
            original_path="unsupported.zip",
            exclusion_reason="Unsupported Extension",
            is_included=False,
            ai_gcs_uris=[],
        ),
        MagicMock(
            original_path="conversion_failed.docx",
            exclusion_reason="Conversion Failed",
            is_included=False,
            ai_gcs_uris=[],
        ),
        MagicMock(original_path="included.pdf", exclusion_reason=None, is_included=True, ai_gcs_uris=["uri1"]),
    ]

    _, warnings = analysis_service._select_files_by_token_limit(candidates, mock_procurement)

    assert len(warnings) == 2
    assert "Arquivos ignorados por 'Unsupported Extension': unsupported.zip" in warnings
    assert "Arquivos ignorados por 'Conversion Failed': conversion_failed.docx" in warnings


def test_process_analysis_from_message_procurement_not_found(
    analysis_service: AnalysisService, caplog: pytest.LogCaptureFixture
) -> None:
    """Tests processing a message when the procurement is not found."""
    analysis_id = uuid.uuid4()
    mock_analysis = MagicMock()
    mock_analysis.procurement_control_number = "PNCP123"
    mock_analysis.version_number = 1
    analysis_service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    analysis_service.procurement_repo.get_procurement_by_id_and_version.return_value = None

    analysis_service.process_analysis_from_message(analysis_id)

    assert f"Procurement {mock_analysis.procurement_control_number} " in caplog.text
    assert "not found" in caplog.text


def test_pre_analyze_procurement_hash_exists(analysis_service: AnalysisService, mock_procurement: MagicMock) -> None:
    """Tests that pre-analysis is skipped if a procurement with the same hash exists."""
    analysis_service.procurement_repo.process_procurement_documents.return_value = []
    analysis_service._calculate_procurement_hash = MagicMock(return_value="existing_hash")
    analysis_service.procurement_repo.get_procurement_by_hash.return_value = MagicMock()

    analysis_service._pre_analyze_procurement(mock_procurement, {})

    analysis_service.procurement_repo.save_procurement_version.assert_not_called()
