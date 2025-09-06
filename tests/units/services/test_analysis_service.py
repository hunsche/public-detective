import unittest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

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
        "budget_ledger_repo": MagicMock(),
        "ai_provider": MagicMock(),
        "gcs_provider": MagicMock(),
        "pubsub_provider": MagicMock(),
    }


def test_get_procurement_overall_status_not_found(mock_dependencies):
    """
    Tests that get_procurement_overall_status returns None when the analysis
    is not found.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_procurement_overall_status.return_value = None
    procurement_control_number = "12345"

    # Act
    result = service.get_procurement_overall_status(procurement_control_number)

    # Assert
    assert result is None
    service.analysis_repo.get_procurement_overall_status.assert_called_once_with(procurement_control_number)


def test_get_procurement_overall_status_found(mock_dependencies):
    """
    Tests that get_procurement_overall_status returns the status when found.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    expected_status = {"status": "ANALYSIS_SUCCESSFUL"}
    service.analysis_repo.get_procurement_overall_status.return_value = expected_status
    procurement_control_number = "12345"

    # Act
    result = service.get_procurement_overall_status(procurement_control_number)

    # Assert
    assert result == expected_status
    service.analysis_repo.get_procurement_overall_status.assert_called_once_with(procurement_control_number)


def test_trigger_ranked_analyses_no_pending_analyses(mock_dependencies):
    """
    Tests that trigger_ranked_analyses does nothing when there are no pending
    analyses.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_pending_analyses_ranked.return_value = []

    # Act
    triggered_count = service.trigger_ranked_analyses(daily_budget=Decimal("100"), zero_vote_budget_percentage=Decimal("10"))

    # Assert
    assert triggered_count == 0
    service.analysis_repo.get_pending_analyses_ranked.assert_called_once()


def test_trigger_ranked_analyses_budget_exceeded(mock_dependencies):
    """
    Tests that trigger_ranked_analyses stops when the budget is exceeded.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    analysis = MagicMock(spec=AnalysisResult)
    analysis.analysis_id = uuid4()
    analysis.procurement_control_number = "123"
    analysis.version_number = 1
    analysis.status = "PENDING_ANALYSIS"
    analysis.retry_count = 0
    analysis.document_hash = "hash"
    analysis.input_tokens_used = 1_000_000
    analysis.output_tokens_used = 1_000_000
    analysis.votes_count = 1
    service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis]

    # Act
    triggered_count = service.trigger_ranked_analyses(daily_budget=Decimal("1"), zero_vote_budget_percentage=Decimal("10"))

    # Assert
    assert triggered_count == 0
    service.analysis_repo.get_pending_analyses_ranked.assert_called_once()


def test_trigger_ranked_analyses_triggers_successfully(mock_dependencies):
    """
    Tests that trigger_ranked_analyses triggers an analysis successfully.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    analysis = MagicMock(spec=AnalysisResult)
    analysis.analysis_id = uuid4()
    analysis.procurement_control_number = "123"
    analysis.version_number = 1
    analysis.status = "PENDING_ANALYSIS"
    analysis.retry_count = 0
    analysis.document_hash = "hash"
    analysis.input_tokens_used = 100_000
    analysis.output_tokens_used = 100_000
    analysis.votes_count = 1
    service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis]
    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        # Act
        triggered_count = service.trigger_ranked_analyses(
            daily_budget=Decimal("100"), zero_vote_budget_percentage=Decimal("10")
        )

        # Assert
        assert triggered_count == 1
        mock_run_specific.assert_called_once_with(analysis.analysis_id)
        service.budget_ledger_repo.save_expense.assert_called_once()


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


def test_process_analysis_from_message_analysis_not_found(mock_dependencies):
    """
    Tests that process_analysis_from_message handles the case where the
    analysis is not found.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.analysis_repo.get_analysis_by_id.return_value = None

    # Act
    service.process_analysis_from_message(analysis_id)

    # Assert
    service.analysis_repo.get_analysis_by_id.assert_called_once_with(analysis_id)
    service.procurement_repo.get_procurement_by_id_and_version.assert_not_called()


def test_process_analysis_from_message_procurement_not_found(mock_dependencies):
    """
    Tests that process_analysis_from_message handles the case where the
    procurement is not found.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    analysis = MagicMock()
    analysis.procurement_control_number = "123"
    analysis.version_number = 1
    service.analysis_repo.get_analysis_by_id.return_value = analysis
    service.procurement_repo.get_procurement_by_id_and_version.return_value = None

    # Act
    service.process_analysis_from_message(analysis_id)

    # Assert
    service.procurement_repo.get_procurement_by_id_and_version.assert_called_once_with("123", 1)


def test_process_analysis_from_message_successful_analysis(mock_dependencies, mock_procurement):
    """
    Tests the successful processing of an analysis from a message.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    analysis = MagicMock()
    analysis.procurement_control_number = "123"
    analysis.version_number = 1
    service.analysis_repo.get_analysis_by_id.return_value = analysis
    service.procurement_repo.get_procurement_by_id_and_version.return_value = mock_procurement

    with patch.object(service, "analyze_procurement") as mock_analyze_procurement:
        # Act
        service.process_analysis_from_message(analysis_id)

        # Assert
        mock_analyze_procurement.assert_called_once_with(mock_procurement, 1, analysis_id, None)
        service.analysis_repo.update_analysis_status.assert_called_once_with(
            analysis_id, ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL
        )


def test_analyze_procurement_no_files_found(mock_dependencies, mock_procurement):
    """
    Tests that analyze_procurement handles the case where no files are found.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.process_procurement_documents.return_value = []

    # Act
    service.analyze_procurement(mock_procurement, 1, uuid4())

    # Assert
    service.procurement_repo.process_procurement_documents.assert_called_once_with(mock_procurement)
    service.analysis_repo.get_analysis_by_hash.assert_not_called()


def test_analyze_procurement_reusing_existing_analysis(mock_dependencies, mock_procurement):
    """
    Tests that analyze_procurement reuses an existing analysis if a matching
    hash is found.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    existing_analysis = MagicMock(spec=AnalysisResult)
    existing_analysis.ai_analysis = MagicMock(spec=Analysis)
    existing_analysis.ai_analysis.risk_score = 5
    existing_analysis.ai_analysis.risk_score_rationale = "Rationale"
    existing_analysis.ai_analysis.procurement_summary = "Summary"
    existing_analysis.ai_analysis.analysis_summary = "Summary"
    existing_analysis.ai_analysis.red_flags = []
    existing_analysis.ai_analysis.seo_keywords = []
    existing_analysis.warnings = []
    existing_analysis.input_tokens_used = 100
    existing_analysis.output_tokens_used = 50
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    service.analysis_repo.get_analysis_by_hash.return_value = existing_analysis

    # Act
    service.analyze_procurement(mock_procurement, 1, analysis_id)

    # Assert
    service.analysis_repo.save_analysis.assert_called_once()
    service.file_record_repo.save_file_record.assert_called_once()
    service.ai_provider.get_structured_analysis.assert_not_called()


def test_analyze_procurement_new_analysis(mock_dependencies, mock_procurement):
    """
    Tests the successful creation of a new analysis.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    service.analysis_repo.get_analysis_by_hash.return_value = None
    mock_ai_analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Rationale",
        procurement_summary="Summary",
        analysis_summary="Summary",
        red_flags=[],
    )
    service.ai_provider.get_structured_analysis.return_value = (mock_ai_analysis, 100, 50)

    # Act
    service.analyze_procurement(mock_procurement, 1, analysis_id)

    # Assert
    service.ai_provider.get_structured_analysis.assert_called_once()
    service.analysis_repo.save_analysis.assert_called_once()
    service.file_record_repo.save_file_record.assert_called_once()
