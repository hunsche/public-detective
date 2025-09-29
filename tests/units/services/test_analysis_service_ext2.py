from unittest.mock import MagicMock, patch

import pytest
from public_detective.models.procurements import Procurement
from public_detective.repositories.procurements import ProcessedFile
from public_detective.services.analysis import AnalysisService


@pytest.fixture
def mock_procurement_repo():
    return MagicMock()


@pytest.fixture
def mock_analysis_repo():
    return MagicMock()


@pytest.fixture
def mock_source_document_repo():
    return MagicMock()


@pytest.fixture
def mock_file_record_repo():
    return MagicMock()


@pytest.fixture
def mock_status_history_repo():
    return MagicMock()


@pytest.fixture
def mock_budget_ledger_repo():
    return MagicMock()


@pytest.fixture
def mock_ai_provider():
    return MagicMock()


@pytest.fixture
def mock_gcs_provider():
    return MagicMock()


@pytest.fixture
def analysis_service(
    mock_procurement_repo,
    mock_analysis_repo,
    mock_source_document_repo,
    mock_file_record_repo,
    mock_status_history_repo,
    mock_budget_ledger_repo,
    mock_ai_provider,
    mock_gcs_provider,
):
    """Provides an AnalysisService instance with mocked dependencies."""
    return AnalysisService(
        procurement_repo=mock_procurement_repo,
        analysis_repo=mock_analysis_repo,
        source_document_repo=mock_source_document_repo,
        file_record_repo=mock_file_record_repo,
        status_history_repo=mock_status_history_repo,
        budget_ledger_repo=mock_budget_ledger_repo,
        ai_provider=mock_ai_provider,
        gcs_provider=mock_gcs_provider,
    )


def test_prepare_ai_candidates_unsupported_extension(analysis_service):
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
def test_prepare_ai_candidates_docx_conversion(mock_converter, analysis_service):
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
def test_prepare_ai_candidates_rtf_conversion(mock_converter, analysis_service):
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
def test_prepare_ai_candidates_doc_conversion(mock_converter, analysis_service):
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
def test_prepare_ai_candidates_bmp_conversion(mock_converter, analysis_service):
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
def test_prepare_ai_candidates_gif_conversion(mock_converter, analysis_service):
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
def test_prepare_ai_candidates_spreadsheet_conversion(mock_converter, analysis_service):
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
def test_prepare_ai_candidates_conversion_failure(mock_converter, analysis_service):
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


def test_get_priority(analysis_service):
    """Tests the file prioritization logic."""
    assert analysis_service._get_priority("edital.pdf") == 0
    assert analysis_service._get_priority("termo de referencia.docx") == 1
    assert analysis_service._get_priority("planilha_de_custos.xlsx") == 3
    assert analysis_service._get_priority("outro_documento.txt") == len(analysis_service._FILE_PRIORITY_ORDER)


@patch("public_detective.services.analysis.AnalysisService._build_analysis_prompt")
def test_select_files_by_token_limit_all_fit(mock_build_prompt, analysis_service):
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
def test_select_files_by_token_limit_some_excluded(mock_build_prompt, analysis_service):
    """Tests file selection when some files exceed the token limit."""
    mock_build_prompt.return_value = "prompt"
    analysis_service.ai_provider.count_tokens_for_analysis.side_effect = [(100, 0, 0), (200000, 0, 0)]

    candidates = [
        MagicMock(original_path="file1.pdf", exclusion_reason=None, ai_gcs_uris=["uri1"], is_included=False),
        MagicMock(original_path="file2.pdf", exclusion_reason=None, ai_gcs_uris=["uri2"], is_included=False),
    ]
    analysis_service.config.GCP_GEMINI_MAX_INPUT_TOKENS = 150

    selected, warnings = analysis_service._select_files_by_token_limit(candidates, MagicMock())

    assert selected[0].is_included
    assert not selected[1].is_included
    assert "limite de 150 tokens foi excedido" in selected[1].exclusion_reason
    assert "foram ignorados" in warnings[0]


@patch("public_detective.services.analysis.AnalysisService._build_analysis_prompt")
def test_select_files_by_token_limit_prioritization(mock_build_prompt, analysis_service):
    """Tests that high-priority files are selected first."""
    mock_build_prompt.return_value = "prompt"
    analysis_service.ai_provider.count_tokens_for_analysis.side_effect = [(100, 0, 0), (200000, 0, 0)]

    candidates = [
        MagicMock(original_path="outro.pdf", exclusion_reason=None, ai_gcs_uris=["uri2"], is_included=False),
        MagicMock(original_path="edital.pdf", exclusion_reason=None, ai_gcs_uris=["uri1"], is_included=False),
    ]
    analysis_service.config.GCP_GEMINI_MAX_INPUT_TOKENS = 150

    selected, warnings = analysis_service._select_files_by_token_limit(candidates, MagicMock())

    # After sorting, edital.pdf is at index 0 and outro.pdf is at index 1
    assert selected[0].is_included
    assert not selected[1].is_included
    assert "limite de 150 tokens foi excedido" in selected[1].exclusion_reason
