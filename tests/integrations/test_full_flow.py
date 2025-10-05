import json
from datetime import date
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from public_detective.models.analyses import Analysis
from public_detective.models.procurements import Procurement
from public_detective.providers.ai import AiProvider
from public_detective.providers.gcs import GcsProvider
from public_detective.providers.pubsub import PubSubProvider
from public_detective.repositories.analyses import AnalysisRepository
from public_detective.repositories.budget_ledger import BudgetLedgerRepository
from public_detective.repositories.file_records import FileRecordsRepository
from public_detective.repositories.procurements import ProcurementsRepository
from public_detective.repositories.source_documents import SourceDocumentsRepository
from public_detective.repositories.status_history import StatusHistoryRepository
from public_detective.services.analysis import AnalysisService
from sqlalchemy.engine import Engine


def load_fixture(path: str) -> Any:
    """Loads a JSON fixture from the specified path.

    Args:
        path: The path to the fixture.

    Returns:
        The loaded JSON data.
    """
    with open(path) as f:
        return json.load(f)


def load_binary_fixture(path: str) -> bytes:
    """Loads a binary fixture from the specified path.

    Args:
        path: The path to the fixture.

    Returns:
        The loaded binary data.
    """
    with open(path, "rb") as f:
        return f.read()


@pytest.fixture
def mock_procurement() -> Procurement:
    """Fixture to create a standard procurement object for tests.

    Returns:
        A procurement object.
    """
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
        "numeroControlePNCP": "123456789-1-1234-2025",
        "dataAtualizacaoGlobal": "2025-01-01T12:00:00",
        "modoDisputaId": 5,
        "situacaoCompraId": 1,
        "usuarioNome": "Test User",
    }
    return Procurement.model_validate(procurement_data)


@pytest.mark.timeout(180)
def test_pre_analysis_flow_integration(db_session: Engine, mock_procurement: Procurement) -> None:
    """
    Tests the pre-analysis flow, mocking external HTTP calls but hitting the DB.

    Args:
        db_session: The SQLAlchemy engine.
        mock_procurement: A mock procurement object.
    """
    db_engine = db_session
    pubsub_provider = PubSubProvider()
    gcs_provider = GcsProvider()
    ai_provider = AiProvider(Analysis)
    analysis_repo = AnalysisRepository(engine=db_engine)
    file_record_repo = FileRecordsRepository(engine=db_engine)
    procurement_repo = ProcurementsRepository(engine=db_engine, pubsub_provider=pubsub_provider)
    status_history_repo = StatusHistoryRepository(engine=db_engine)
    budget_ledger_repo = BudgetLedgerRepository(engine=db_engine)
    source_document_repo = SourceDocumentsRepository(engine=db_engine)
    analysis_service = AnalysisService(
        procurement_repo=procurement_repo,
        analysis_repo=analysis_repo,
        source_document_repo=source_document_repo,
        file_record_repo=file_record_repo,
        status_history_repo=status_history_repo,
        budget_ledger_repo=budget_ledger_repo,
        ai_provider=ai_provider,
        gcs_provider=gcs_provider,
        pubsub_provider=pubsub_provider,
    )

    with (
        patch.object(procurement_repo, "get_updated_procurements_with_raw_data", return_value=[(mock_procurement, {})]),
        patch.object(procurement_repo, "process_procurement_documents", return_value=[]),
        patch.object(procurement_repo, "get_procurement_by_hash", return_value=False),
        patch.object(analysis_repo, "save_pre_analysis", return_value=uuid4()) as save_pre_analysis_mock,
    ):
        analysis_service.run_pre_analysis(date(2025, 1, 1), date(2025, 1, 1), 10, 60, None)

    save_pre_analysis_mock.assert_called_once()
