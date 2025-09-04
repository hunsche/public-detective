"""
Unit tests for the AnalysisService pre-analysis logic.
"""

from datetime import date
from unittest.mock import MagicMock, patch

import pytest
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


def test_run_pre_analysis_no_procurements_found(mock_dependencies):
    """Tests that the pre-analysis job handles dates with no procurements."""
    # Arrange
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = []
    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 1)

    # Act
    with patch.object(service, "_pre_analyze_procurement") as mock_pre_analyze:
        service.run_pre_analysis(start_date, end_date, batch_size=10, sleep_seconds=0)

    # Assert
    mock_pre_analyze.assert_not_called()
    assert service.procurement_repo.get_updated_procurements_with_raw_data.call_count == 1


def test_pre_analyze_procurement_idempotency(mock_dependencies, mock_procurement):
    """
    Tests that _pre_analyze_procurement skips processing if a procurement
    with the same hash already exists.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    raw_data = {"key": "value"}
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    service.procurement_repo.get_procurement_by_hash.return_value = (
        mock_procurement  # Simulate finding an existing hash
    )

    # Act
    service._pre_analyze_procurement(mock_procurement, raw_data)

    # Assert
    service.procurement_repo.get_latest_version.assert_not_called()
    service.procurement_repo.save_procurement_version.assert_not_called()
    service.analysis_repo.save_pre_analysis.assert_not_called()


def test_run_pre_analysis_sleeps_between_batches(mock_dependencies, mock_procurement):
    """
    Tests that the pre-analysis job sleeps between processing batches.
    """
    # Arrange
    service = AnalysisService(**mock_dependencies)
    # Simulate two procurements to trigger two batches
    procurements = [(mock_procurement, {}), (mock_procurement, {})]
    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = procurements
    start_date = date(2025, 1, 1)
    end_date = date(2025, 1, 1)

    # Act
    with patch("time.sleep") as mock_sleep:
        service.run_pre_analysis(start_date, end_date, batch_size=1, sleep_seconds=5)

    # Assert
    mock_sleep.assert_called_once_with(5)
