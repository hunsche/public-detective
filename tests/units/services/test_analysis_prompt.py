"""This module contains tests for the analysis prompt generation."""

from datetime import datetime
from unittest.mock import MagicMock

from public_detective.models.procurements import Procurement
from public_detective.services.analysis import AnalysisService


def test_build_analysis_prompt_contains_new_instructions() -> None:
    """Tests if the generated prompt includes the new detailed instructions."""
    # Arrange
    mock_procurement_repo = MagicMock()
    mock_analysis_repo = MagicMock()
    mock_source_document_repo = MagicMock()
    mock_file_record_repo = MagicMock()
    mock_status_history_repo = MagicMock()
    mock_budget_ledger_repo = MagicMock()
    mock_ai_provider = MagicMock()
    mock_gcs_provider = MagicMock()

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

    procurement_data = {
        "processo": "123/2023",
        "objetoCompra": "Test Procurement",
        "amparoLegal": {"codigo": 1, "nome": "Lei 14.133/2021", "descricao": "Nova Lei de Licitações"},
        "srp": False,
        "orgaoEntidade": {
            "cnpj": "00000000000191",
            "razaoSocial": "Test Entity",
            "poderId": "E",
            "esferaId": "M",
        },
        "anoCompra": 2023,
        "sequencialCompra": 1,
        "dataPublicacaoPncp": datetime.now().isoformat(),
        "dataAtualizacao": datetime.now().isoformat(),
        "numeroCompra": "001/2023",
        "unidadeOrgao": {
            "ufNome": "Test State",
            "codigoUnidade": "123",
            "nomeUnidade": "Test Unit",
            "ufSigla": "TS",
            "municipioNome": "Test City",
            "codigoIbge": "1234567",
        },
        "modalidadeId": 1,
        "numeroControlePNCP": "12345678901234567890-1-0001/2023",
        "dataAtualizacaoGlobal": datetime.now().isoformat(),
        "modoDisputaId": 1,
        "situacaoCompraId": 1,
        "usuarioNome": "Test User",
        "valorTotalEstimado": 1000.0,
        "dataAberturaProposta": None,
        "dataEncerramentoProposta": None,
    }
    procurement = Procurement.model_validate(procurement_data)

    # Act
    prompt = service._build_analysis_prompt(procurement, [])

    # Assert
    assert "SUPERFATURAMENTO" in prompt
    assert "Critérios para a Nota de Risco (0 a 10):" in prompt
    assert "0-1 (Risco Mínimo):" in prompt
    assert "Classificação de Severidade:" in prompt
    assert "Sempre que apontar sobrepreço, cite a fonte de sua referência" in prompt
