import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from public_detective.models.analyses import Analysis, AnalysisResult
from public_detective.models.procurements import Procurement
from public_detective.services.analysis import AIFileCandidate, AnalysisService


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
def mock_valid_analysis():
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
def mock_ai_provider(mock_valid_analysis):
    provider = MagicMock()
    provider.get_structured_analysis.return_value = (mock_valid_analysis, 100, 50, 10)
    return provider


@pytest.fixture
def mock_gcs_provider():
    return MagicMock()


@pytest.fixture
def mock_pricing_service():
    service = MagicMock()
    service.calculate.return_value = (Decimal("1"), Decimal("1"), Decimal("1"), Decimal("3"))
    return service


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
    mock_pricing_service,
):
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
    )
    service.pricing_service = mock_pricing_service
    return service


@patch("public_detective.services.analysis.AnalysisService._get_modality")
@patch("public_detective.services.analysis.AnalysisService._calculate_hash")
def test_analyze_procurement_happy_path(mock_hash, mock_get_modality, analysis_service, mock_valid_analysis):
    """Tests the full, successful execution of the analyze_procurement method."""
    mock_hash.return_value = "testhash"
    mock_get_modality.return_value = "TEXT"

    mock_procurement = MagicMock(spec=Procurement)
    mock_procurement.pncp_control_number = "123"
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

    analysis_service.analyze_procurement(mock_procurement, 1, analysis_id)

    analysis_service.ai_provider.get_structured_analysis.assert_called_once()
    analysis_service.analysis_repo.save_analysis.assert_called_once()

    saved_result: AnalysisResult = analysis_service.analysis_repo.save_analysis.call_args[1]["result"]
    assert saved_result.document_hash == "testhash"
    assert saved_result.analysis_prompt == "prompt"
    assert saved_result.procurement_control_number == "123"
    assert saved_result.ai_analysis == mock_valid_analysis