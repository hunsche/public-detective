"""
Integration tests for the full analysis pipeline.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
from models.analysis import Analysis
from models.procurement import Procurement
from services.analysis import AnalysisService
from alembic.config import Config
from alembic import command


@pytest.fixture(scope="function", autouse=True)
def run_migrations(monkeypatch):
    """
    Runs alembic migrations on the test database before any tests are run.
    """
    monkeypatch.setenv("POSTGRES_HOST", "localhost")
    monkeypatch.setenv("POSTGRES_DB", "public_detective")
    monkeypatch.setenv("POSTGRES_USER", "postgres")
    monkeypatch.setenv("POSTGRES_PASSWORD", "postgres")

    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    yield


@pytest.mark.integration
@patch("services.analysis.AiProvider")
@patch("services.analysis.ProcurementRepository")
@patch("services.analysis.AnalysisRepository")
def test_full_analysis_and_idempotency(
    mock_analysis_repo, mock_proc_repo, mock_ai_provider, monkeypatch
):
    """
    Tests the full analysis flow, including saving to the database
    and the idempotency check on a second run.
    """
    monkeypatch.setenv("GCP_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("STORAGE_EMULATOR_HOST", "http://localhost:8086")

    file_content = b"This is a test document."
    ai_response = Analysis(
        risk_score=7,
        risk_score_rationale="High risk detected.",
        summary="This is a summary.",
        red_flags=[],
    )

    mock_proc_repo.return_value.process_procurement_documents.return_value = (
        [("test.docx", file_content)], [("test.docx", file_content)]
    )
    mock_ai_provider.return_value.get_structured_analysis.return_value = ai_response

    service = AnalysisService()
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
        "numeroControlePNCP": "integration-test-123",
        "dataAtualizacaoGlobal": "2025-01-01T12:00:00",
        "modoDisputaId": 5,
        "situacaoCompraId": 1,
        "usuarioNome": "Test User",
    }
    procurement = Procurement.model_validate(procurement_data)

    # First run
    mock_analysis_repo.return_value.get_analysis_by_hash.return_value = None
    service.analyze_procurement(procurement)

    # Assertions for First Run
    mock_analysis_repo.return_value.save_analysis.assert_called_once()
    saved_result = mock_analysis_repo.return_value.save_analysis.call_args[0][0]

    # Second run should be idempotent
    mock_analysis_repo.return_value.get_analysis_by_hash.return_value = saved_result
    service.analyze_procurement(procurement)

    # Assert that save was not called again
    mock_analysis_repo.return_value.save_analysis.assert_called_once()
