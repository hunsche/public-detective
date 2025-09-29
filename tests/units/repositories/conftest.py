from unittest.mock import MagicMock, patch

import pytest
from public_detective.models.procurements import Procurement
from public_detective.repositories.procurements import ProcurementsRepository


@pytest.fixture
def mock_engine() -> MagicMock:
    """Fixture for a mocked database engine."""
    return MagicMock()


@pytest.fixture
def mock_pubsub_provider() -> MagicMock:
    """Fixture for a mocked PubSubProvider."""
    return MagicMock()


@pytest.fixture
def repo(mock_engine: MagicMock, mock_pubsub_provider: MagicMock) -> ProcurementsRepository:
    """Provides a ProcurementsRepository instance with mocked dependencies."""
    with (
        patch("public_detective.repositories.procurements.LoggingProvider") as mock_logging_provider,
        patch("public_detective.repositories.procurements.ConfigProvider") as mock_config_provider,
    ):

        mock_logger = MagicMock()
        mock_config = MagicMock()
        mock_config.PNCP_PUBLIC_QUERY_API_URL = "http://test.api/"
        mock_config.PNCP_INTEGRATION_API_URL = "http://test.api/"

        mock_logging_provider.return_value.get_logger.return_value = mock_logger
        mock_config_provider.get_config.return_value = mock_config

        repository = ProcurementsRepository(engine=mock_engine, pubsub_provider=mock_pubsub_provider)
        repository.logger = mock_logger
        repository.config = mock_config
        return repository


@pytest.fixture
def mock_procurement() -> Procurement:
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
