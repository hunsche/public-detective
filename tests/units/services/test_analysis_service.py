"""
Unit tests for the AnalysisService.
"""

from datetime import date
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from constants.analysis_feedback import ExclusionReason, Warnings
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
        "budget_ledger_repo": MagicMock(),
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
    service.analyze_procurement(mock_procurement, 1, uuid4())

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


def test_idempotency_check_with_gcs_test_prefix(mock_dependencies, mock_procurement):
    """
    Tests that the GCS path includes the test prefix during an idempotency check.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    service.config.GCP_GCS_TEST_PREFIX = "test-prefix"
    mock_dependencies["procurement_repo"].process_procurement_documents.return_value = [("file.pdf", b"content")]

    mock_ai_analysis = MagicMock(spec=Analysis)
    mock_ai_analysis.risk_score = 5
    mock_ai_analysis.risk_score_rationale = "Reused"
    mock_ai_analysis.procurement_summary = "Reused"
    mock_ai_analysis.analysis_summary = "Reused"
    mock_ai_analysis.red_flags = []
    mock_ai_analysis.seo_keywords = []

    mock_existing_analysis = MagicMock(spec=AnalysisResult)
    mock_existing_analysis.ai_analysis = mock_ai_analysis
    mock_existing_analysis.warnings = []
    mock_existing_analysis.input_tokens_used = 1
    mock_existing_analysis.output_tokens_used = 1

    mock_dependencies["analysis_repo"].get_analysis_by_hash.return_value = mock_existing_analysis

    # Act
    service.analyze_procurement(mock_procurement, 1, uuid4())

    # Assert
    # Check that save_analysis was called with the correct GCS path
    call_args, _ = mock_dependencies["analysis_repo"].save_analysis.call_args
    saved_result = call_args[1]
    assert saved_result.original_documents_gcs_path.startswith("test-prefix/")


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
    service.analyze_procurement(mock_procurement, 1, uuid4())

    # Assert
    assert mock_dependencies["file_record_repo"].save_file_record.call_count == 2


def test_select_and_prepare_files_for_ai_all_scenarios(mock_dependencies):
    """Tests all filtering scenarios in _select_and_prepare_files_for_ai."""
    # Arrange
    service = AnalysisService(**mock_dependencies)
    max_files = 3
    max_size_bytes = 50
    max_size_mb = max_size_bytes / 1024 / 1024
    service._MAX_FILES_FOR_AI = max_files
    service._MAX_SIZE_BYTES_FOR_AI = max_size_bytes

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
    assert excluded["unsupported.txt"] == ExclusionReason.UNSUPPORTED_EXTENSION
    assert excluded["limit_exceeded.pdf"] == ExclusionReason.FILE_LIMIT_EXCEEDED.format(max_files=max_files)
    assert excluded["another.pdf"] == ExclusionReason.FILE_LIMIT_EXCEEDED.format(max_files=max_files)
    assert excluded["oversized.pdf"] == ExclusionReason.TOTAL_SIZE_LIMIT_EXCEEDED.format(max_size_mb=max_size_mb)

    assert len(warnings) == 2
    assert warnings[0] == Warnings.FILE_LIMIT_EXCEEDED.format(
        max_files=max_files, ignored_files="another.pdf, limit_exceeded.pdf"
    )
    assert warnings[1] == Warnings.TOTAL_SIZE_LIMIT_EXCEEDED.format(
        max_size_mb=max_size_mb, ignored_files="oversized.pdf"
    )


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

    service.analyze_procurement(mock_procurement, 1, uuid4())

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
    max_output_tokens = 1024
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
        service.process_analysis_from_message(analysis_id, max_output_tokens=max_output_tokens)

        # Assert
        mock_analyze_procurement.assert_called_once_with(mock_procurement, 1, analysis_id, max_output_tokens)
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


def test_analyze_procurement_with_gcs_test_prefix(mock_dependencies, mock_procurement):
    """
    Tests that the GCS path includes the test prefix when the config is set.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    service.config.GCP_GCS_TEST_PREFIX = "test-prefix"
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"c")]
    service.analysis_repo.get_analysis_by_hash.return_value = None
    mock_ai_analysis = MagicMock(spec=Analysis)
    mock_ai_analysis.model_dump.return_value = {
        "risk_score": 1,
        "procurement_summary": "test",
        "analysis_summary": "test",
    }
    service.ai_provider.get_structured_analysis.return_value = (mock_ai_analysis, 100, 50)

    # Act
    service.analyze_procurement(mock_procurement, 1, uuid4())

    # Assert
    # Check the call to _upload_analysis_report
    _, kwargs = service.gcs_provider.upload_file.call_args_list[0]
    destination_blob_name = kwargs["destination_blob_name"]
    assert destination_blob_name.startswith("test-prefix/")

    # Check the call to save_file_record
    call_args, _ = service.file_record_repo.save_file_record.call_args
    file_record = call_args[0]
    assert file_record.gcs_path.startswith("test-prefix/")


def test_run_pre_analysis_with_max_messages(mock_dependencies, mock_procurement):
    """
    Tests that pre-analysis stops when max_messages is reached.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    procurements = [(mock_procurement, {}), (mock_procurement, {})]
    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = procurements

    with patch.object(service, "_pre_analyze_procurement") as mock_pre_analyze:
        # Act
        service.run_pre_analysis(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 1),
            batch_size=1,
            sleep_seconds=0,
            max_messages=1,
        )

        # Assert
        mock_pre_analyze.assert_called_once()


def test_run_pre_analysis_exception_handling(mock_dependencies, mock_procurement):
    """
    Tests that the pre-analysis loop continues even if one procurement fails.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    service.logger = MagicMock()
    procurements = [
        (mock_procurement, {"id": "1"}),
        (mock_procurement, {"id": "2"}),
    ]
    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = procurements

    with patch.object(
        service, "_pre_analyze_procurement", side_effect=[Exception("Test Error"), None]
    ) as mock_pre_analyze:
        # Act
        service.run_pre_analysis(
            start_date=date(2025, 1, 1),
            end_date=date(2025, 1, 1),
            batch_size=2,
            sleep_seconds=0,
        )

        # Assert
        assert mock_pre_analyze.call_count == 2
        # Check that the logger was called with the error
        service.logger.error.assert_called_with(
            f"Failed to pre-analyze procurement {mock_procurement.pncp_control_number}: Test Error",
            exc_info=True,
        )
