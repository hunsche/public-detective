"""
Unit tests for the AnalysisService.
"""

from datetime import date
from unittest.mock import MagicMock

import pytest
from models.analysis import Analysis, AnalysisResult
from models.procurement import Procurement
from services.analysis import AnalysisService


@pytest.fixture
def mock_dependencies():
    """Fixture to create all mocked dependencies for AnalysisService."""
    return {
        "procurement_repo": MagicMock(),
        "analysis_repo": MagicMock(),
        "file_record_repo": MagicMock(),
        "ai_provider": MagicMock(),
        "gcs_provider": MagicMock(),
        "pubsub_provider": MagicMock(),
    }


@pytest.fixture
def mock_procurement():
    """Fixture to create a standard procurement object for tests."""
    procurement_data = {
        "processo": "123",
        "objetoCompra": "Test Object",
        "amparoLegal": {"codigo": 1, "nome": "Test", "descricao": "Test"},
        "srp": False,
        "orgaoEntidade": {
            "cnpj": "00000000000191",
            "razaoSocial": "Test Entity",
            "poderId": "E",
            "esferaId": "F",
        },
        "anoCompra": 2025,
        "sequencialCompra": 1,
        "dataPublicacaoPncp": "2025-01-01T12:00:00",
        "dataAtualizacao": "2025-01-01T12:00:00",
        "numeroCompra": "1",
        "unidadeOrgao": {
            "ufNome": "Test",
            "codigoUnidade": "1",
            "nomeUnidade": "Test",
            "ufSigla": "TE",
            "municipioNome": "Test",
            "codigoIbge": "1",
        },
        "modalidadeId": 8,
        "numeroControlePNCP": "123",
        "dataAtualizacaoGlobal": "2025-01-01T12:00:00",
        "modoDisputaId": 5,
        "situacaoCompraId": 1,
        "usuarioNome": "Test User",
    }
    return Procurement.model_validate(procurement_data)


def test_analysis_service_instantiation(mock_dependencies):
    """Tests that the AnalysisService can be instantiated correctly."""
    service = AnalysisService(**mock_dependencies)
    assert service is not None
    assert service.procurement_repo == mock_dependencies["procurement_repo"]


def test_idempotency_check(mock_dependencies, mock_procurement):
    """Tests that analysis is skipped if a result with the same hash exists."""
    # Arrange: Mock the return values
    mock_dependencies["procurement_repo"].process_procurement_documents.return_value = [("file.pdf", b"content")]
    mock_existing_analysis = MagicMock(spec=AnalysisResult)
    mock_existing_analysis.ai_analysis = MagicMock(spec=Analysis)
    mock_dependencies["analysis_repo"].get_analysis_by_hash.return_value = mock_existing_analysis

    # Act
    service = AnalysisService(**mock_dependencies)
    service.analyze_procurement(mock_procurement, 1, 123)

    # Assert: Check that the AI provider was not called
    mock_dependencies["ai_provider"].get_structured_analysis.assert_not_called()


def test_save_file_record_called_for_each_file(mock_dependencies, mock_procurement):
    """Tests that save_file_record is called for each file."""
    # Arrange
    mock_dependencies["procurement_repo"].process_procurement_documents.return_value = [
        ("file1.pdf", b"content1"),
        ("file2.pdf", b"content2"),
    ]
    mock_dependencies["analysis_repo"].get_analysis_by_hash.return_value = None
    mock_dependencies["analysis_repo"].save_analysis.return_value = 123
    mock_dependencies["ai_provider"].get_structured_analysis.return_value = Analysis(
        risk_score=1,
        risk_score_rationale="test",
        summary="test",
        red_flags=[],
    )

    # Act
    service = AnalysisService(**mock_dependencies)
    service.analyze_procurement(mock_procurement, 1, 123)

    # Assert
    assert mock_dependencies["file_record_repo"].save_file_record.call_count == 2


def test_select_and_prepare_files_for_ai_all_scenarios(mock_dependencies):
    """Tests all filtering scenarios in _select_and_prepare_files_for_ai."""
    # Arrange
    service = AnalysisService(**mock_dependencies)
    service._MAX_FILES_FOR_AI = 3
    service._MAX_SIZE_BYTES_FOR_AI = 50

    all_files = [
        ("edital.pdf", b"edital content"),  # Priority 0
        ("unsupported.txt", b"unsupported"),
        ("oversized.pdf", b"a" * 60),
        ("another.pdf", b"another content"),  # No priority
        ("planilha.xls", b"planilha content"),  # Priority 3
        ("limit_exceeded.pdf", b"small"),
    ]

    # Act
    files_for_ai, excluded, warnings = service._select_and_prepare_files_for_ai(all_files)

    # Assert
    assert len(files_for_ai) == 2
    assert files_for_ai[0][0] == "edital.pdf"
    assert files_for_ai[1][0] == "planilha.xls"

    assert len(excluded) == 4
    assert excluded["unsupported.txt"] == "Unsupported file extension."
    assert excluded["limit_exceeded.pdf"] == "File limit exceeded."
    # This is also excluded by file limit because it has lower priority than the others
    assert excluded["another.pdf"] == "File limit exceeded."
    assert excluded["oversized.pdf"] == "Total size limit exceeded."

    assert len(warnings) == 2
    assert "Limite de arquivos excedido" in warnings[0]
    # The warning message for size limit is dynamic based on what's left
    assert "excedido" in warnings[1]


def test_analyze_procurement_no_files_found(mock_dependencies, mock_procurement):
    """Tests that the analysis aborts if no documents are found."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.process_procurement_documents.return_value = []

    service.analyze_procurement(mock_procurement, 1, 123)

    service.ai_provider.get_structured_analysis.assert_not_called()


def test_analyze_procurement_no_supported_files(mock_dependencies, mock_procurement):
    """Tests that analysis aborts if no files remain after filtering."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.process_procurement_documents.return_value = [("unsupported.txt", b"c")]

    service.analyze_procurement(mock_procurement, 1, 123)

    service.ai_provider.get_structured_analysis.assert_not_called()


def test_analyze_procurement_main_success_path(mock_dependencies, mock_procurement):
    """Tests the main success path of the analysis pipeline."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"c")]
    service.analysis_repo.get_analysis_by_hash.return_value = None
    mock_ai_analysis = MagicMock(spec=Analysis)
    mock_ai_analysis.model_dump.return_value = {"risk_score": 1, "summary": "test"}
    service.ai_provider.get_structured_analysis.return_value = mock_ai_analysis

    service.analyze_procurement(mock_procurement, 1, 123)

    service.analysis_repo.save_analysis.assert_called_once()
    service.gcs_provider.upload_file.assert_called()
    service.file_record_repo.save_file_record.assert_called_once()


def test_analyze_procurement_exception_handling(mock_dependencies, mock_procurement):
    """Tests that exceptions in the pipeline are caught and logged."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"c")]
    service.analysis_repo.get_analysis_by_hash.return_value = None
    service.ai_provider.get_structured_analysis.side_effect = Exception("AI Error")

    with pytest.raises(Exception, match="AI Error"):
        service.analyze_procurement(mock_procurement, 1, 123)


def test_run_analysis_no_procurements(mock_dependencies):
    """Tests that the loop continues if no procurements are found for a date."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_updated_procurements.return_value = []
    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 1)

    service.run_analysis(start_date, end_date)

    service.procurement_repo.publish_procurement_to_pubsub.assert_not_called()


def test_run_analysis_publish_failure(mock_dependencies, mock_procurement):
    """Tests that the loop continues even if publishing to Pub/Sub fails."""
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_updated_procurements.return_value = [mock_procurement]
    service.procurement_repo.publish_procurement_to_pubsub.return_value = False
    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 1)

    service.run_analysis(start_date, end_date)

    service.procurement_repo.publish_procurement_to_pubsub.assert_called_once_with(mock_procurement)


def test_process_analysis_from_message_analysis_not_found(mock_dependencies):
    """
    Tests that the function returns early if the analysis_id is not found.
    """
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_analysis_by_id.return_value = None

    service.process_analysis_from_message(999)

    service.procurement_repo.get_procurement_by_id_and_version.assert_not_called()


def test_process_analysis_from_message_procurement_not_found(mock_dependencies):
    """
    Tests that the function returns early if the procurement is not found.
    """
    service = AnalysisService(**mock_dependencies)
    mock_analysis = MagicMock()
    mock_analysis.procurement_control_number = "123"
    mock_analysis.version_number = 1
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    service.procurement_repo.get_procurement_by_id_and_version.return_value = None

    service.process_analysis_from_message(123)

    service.analysis_repo.update_analysis_status.assert_not_called()
