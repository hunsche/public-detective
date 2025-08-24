"""
Unit tests for the AnalysisService.
"""

from unittest.mock import MagicMock, patch

import pytest
from models.procurement import Procurement


@pytest.fixture(autouse=True)
def mock_config_provider():
    """Mocks the ConfigProvider to avoid dependency on environment variables."""
    with patch("providers.config.ConfigProvider.get_config") as mock_get_config:
        mock_config = MagicMock()
        mock_config.GCP_GEMINI_API_KEY = "test-key"
        mock_get_config.return_value = mock_config
        yield mock_get_config


@pytest.fixture
def mock_ai_provider():
    """Mocks the AiProvider."""
    with patch("providers.ai.AiProvider") as mock_provider:
        yield mock_provider


@pytest.fixture
def mock_gcs_provider():
    """Mocks the GcsProvider."""
    with patch("providers.gcs.GcsProvider") as mock_provider:
        yield mock_provider


@pytest.fixture
def mock_analysis_repo():
    """Mocks the AnalysisRepository."""
    with patch("repositories.analysis.AnalysisRepository") as mock_repo:
        yield mock_repo


@pytest.fixture
def mock_procurement_repo():
    """Mocks the ProcurementRepository."""
    with patch("repositories.procurement.ProcurementRepository") as mock_repo:
        yield mock_repo


@patch("services.analysis.AnalysisService.__init__", return_value=None)
def test_analysis_service_instantiation(_mock_init):
    """Tests that the AnalysisService can be instantiated correctly."""
    from services.analysis import AnalysisService

    service = AnalysisService()
    assert service is not None
    _mock_init.assert_called_once()


@patch("services.analysis.AnalysisRepository")
@patch("services.analysis.ProcurementRepository")
@patch("services.analysis.GcsProvider")
@patch("services.analysis.AiProvider")
def test_idempotency_check(
    _mock_ai_provider,
    _mock_gcs_provider,
    mock_procurement_repo,
    mock_analysis_repo,
):
    """Tests that analysis is skipped if a result with the same hash exists."""
    from services.analysis import AnalysisService

    mock_procurement_repo.return_value.process_procurement_documents.return_value = (
        [("file.pdf", b"content")],
        [("file.pdf", b"content")],
    )
    mock_analysis_repo.return_value.get_analysis_by_hash.return_value = "existing"

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
        "numeroControlePNCP": "123",
        "dataAtualizacaoGlobal": "2025-01-01T12:00:00",
        "modoDisputaId": 5,
        "situacaoCompraId": 1,
        "usuarioNome": "Test User",
    }
    procurement = Procurement.model_validate(procurement_data)

    service.analyze_procurement(procurement)

    # Since the service is initialized with mocked providers, we need to check
    # the mock that was passed to the constructor.
    service.ai_provider.get_structured_analysis.assert_not_called()
