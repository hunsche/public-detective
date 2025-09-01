"""
Unit tests for the AnalysisService.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
from models.analyses import Analysis, AnalysisResult
from models.procurement_analysis_status import ProcurementAnalysisStatus
from models.procurements import Procurement
from services.analysis import AnalysisService


@pytest.fixture
def mock_dependencies():
    """Fixture to create all mocked dependencies for AnalysisService."""
    return {
        "procurement_repo": MagicMock(),
        "analysis_repo": MagicMock(),
        "file_record_repo": MagicMock(),
        "status_history_repo": MagicMock(),
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

    # Create a mock for the nested ai_analysis object
    mock_ai_analysis_details = MagicMock(spec=Analysis)
    mock_ai_analysis_details.risk_score = 5
    mock_ai_analysis_details.risk_score_rationale = "Reused rationale"
    mock_ai_analysis_details.procurement_summary = "Reused procurement summary"
    mock_ai_analysis_details.analysis_summary = "Reused analysis summary"
    mock_ai_analysis_details.red_flags = []
    mock_ai_analysis_details.seo_keywords = []

    # Create the main mock for the analysis result
    mock_existing_analysis = MagicMock(spec=AnalysisResult)
    mock_existing_analysis.ai_analysis = mock_ai_analysis_details
    mock_existing_analysis.warnings = ["Reused warning"]
    mock_existing_analysis.input_tokens_used = 100
    mock_existing_analysis.output_tokens_used = 50

    mock_dependencies["analysis_repo"].get_analysis_by_hash.return_value = mock_existing_analysis

    # Act
    service = AnalysisService(**mock_dependencies)
    service.analyze_procurement(mock_procurement, 1, 123)

    # Assert: Check that the AI provider was not called
    mock_dependencies["ai_provider"].get_structured_analysis.assert_not_called()

    # Also assert that save_analysis was called with the reused data
    mock_dependencies["analysis_repo"].save_analysis.assert_called_once()
    call_args, _ = mock_dependencies["analysis_repo"].save_analysis.call_args
    saved_result = call_args[1]  # second argument is the AnalysisResult object
    assert saved_result.ai_analysis.risk_score_rationale == "Reused rationale"
    assert saved_result.ai_analysis.procurement_summary == "Reused procurement summary"
    assert saved_result.ai_analysis.analysis_summary == "Reused analysis summary"
    assert saved_result.warnings == ["Reused warning"]


def test_save_file_record_called_for_each_file(mock_dependencies, mock_procurement):
    """Tests that save_file_record is called for each file."""
    # Arrange
    mock_dependencies["procurement_repo"].process_procurement_documents.return_value = [
        ("file1.pdf", b"content1"),
        ("file2.pdf", b"content2"),
    ]
    mock_dependencies["analysis_repo"].get_analysis_by_hash.return_value = None
    mock_dependencies["analysis_repo"].save_analysis.return_value = 123
    mock_dependencies["ai_provider"].get_structured_analysis.return_value = (
        Analysis(
            risk_score=1,
            risk_score_rationale="test",
            procurement_summary="test",
            analysis_summary="test",
            red_flags=[],
        ),
        100,
        50,
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
    mock_ai_analysis.model_dump.return_value = {
        "risk_score": 1,
        "procurement_summary": "test",
        "analysis_summary": "test",
    }
    service.ai_provider.get_structured_analysis.return_value = (mock_ai_analysis, 100, 50)

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


def test_process_analysis_from_message_success(mock_dependencies, mock_procurement):
    """
    Tests the success path of process_analysis_from_message, ensuring history is recorded.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    analysis_id = 123
    mock_analysis_result = MagicMock(spec=AnalysisResult)
    mock_analysis_result.procurement_control_number = "PNCP-123"
    mock_analysis_result.version_number = 1
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis_result
    service.procurement_repo.get_procurement_by_id_and_version.return_value = mock_procurement

    with (
        patch.object(service, "_update_status_with_history") as mock_update_status,
        patch.object(service, "analyze_procurement") as mock_analyze_procurement,
    ):
        # Act
        service.process_analysis_from_message(analysis_id)

        # Assert
        mock_analyze_procurement.assert_called_once_with(mock_procurement, 1, analysis_id)
        mock_update_status.assert_called_once_with(
            analysis_id,
            ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL,
            "Analysis completed successfully.",
        )


def test_process_analysis_from_message_failure(mock_dependencies, mock_procurement):
    """
    Tests the failure path of process_analysis_from_message, ensuring history is recorded.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    analysis_id = 123
    error_message = "AI provider failed"
    mock_analysis_result = MagicMock(spec=AnalysisResult)
    mock_analysis_result.procurement_control_number = "PNCP-123"
    mock_analysis_result.version_number = 1
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis_result
    service.procurement_repo.get_procurement_by_id_and_version.return_value = mock_procurement

    with (
        patch.object(service, "analyze_procurement", side_effect=Exception(error_message)),
        patch.object(service, "_update_status_with_history") as mock_update_status,
    ):
        # Act & Assert
        with pytest.raises(Exception, match=error_message):
            service.process_analysis_from_message(analysis_id)

        mock_update_status.assert_called_once_with(
            analysis_id, ProcurementAnalysisStatus.ANALYSIS_FAILED, error_message
        )


def test_get_procurement_overall_status_calls_repo(mock_dependencies):
    """
    Tests that the service method calls the repository method.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    control_number = "PNCP-123"
    expected_status = {
        "procurement_id": control_number,
        "latest_version": 1,
        "overall_status": "PENDING",
    }
    service.analysis_repo.get_procurement_overall_status.return_value = expected_status

    # Act
    result = service.get_procurement_overall_status(control_number)

    # Assert
    assert result == expected_status
    service.analysis_repo.get_procurement_overall_status.assert_called_once_with(control_number)


def test_get_procurement_overall_status_handles_none(mock_dependencies):
    """
    Tests that the service method handles a None response from the repository.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    control_number = "PNCP-999"
    service.analysis_repo.get_procurement_overall_status.return_value = None

    # Act
    result = service.get_procurement_overall_status(control_number)

    # Assert
    assert result is None
    service.analysis_repo.get_procurement_overall_status.assert_called_once_with(control_number)


def test_reap_stale_analyses(mock_dependencies):
    """
    Tests that the reap_stale_analyses method correctly calls the repository
    and creates history records for each stale analysis.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    stale_ids = [1, 2, 3]
    timeout = 15
    service.analysis_repo.reset_stale_analyses.return_value = stale_ids

    # Act
    result_count = service.reap_stale_analyses(timeout)

    # Assert
    assert result_count == len(stale_ids)
    service.analysis_repo.reset_stale_analyses.assert_called_once_with(timeout)
    assert service.status_history_repo.create_record.call_count == len(stale_ids)
    service.status_history_repo.create_record.assert_any_call(
        1, "TIMEOUT", f"Analysis timed out after {timeout} minutes."
    )
    service.status_history_repo.create_record.assert_any_call(
        3, "TIMEOUT", f"Analysis timed out after {timeout} minutes."
    )
