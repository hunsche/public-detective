from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from public_detective.models.procurements import Procurement
from public_detective.services.analysis import AIFileCandidate, AnalysisService


@pytest.fixture
def mock_procurement_repo():
    return MagicMock()


@pytest.fixture
def mock_analysis_repo():
    return MagicMock()


@pytest.fixture
def mock_source_document_repo():
    return MagicMock()


@pytest.fixture
def mock_file_record_repo():
    return MagicMock()


@pytest.fixture
def mock_status_history_repo():
    return MagicMock()


@pytest.fixture
def mock_budget_ledger_repo():
    return MagicMock()


@pytest.fixture
def mock_ai_provider():
    return MagicMock()


@pytest.fixture
def mock_gcs_provider():
    return MagicMock()


@pytest.fixture
def analysis_service(
    mock_procurement_repo,
    mock_analysis_repo,
    mock_source_document_repo,
    mock_file_record_repo,
    mock_status_history_repo,
    mock_budget_ledger_repo,
    mock_ai_provider,
    mock_gcs_provider,
):
    """Provides an AnalysisService instance with mocked dependencies."""
    return AnalysisService(
        procurement_repo=mock_procurement_repo,
        analysis_repo=mock_analysis_repo,
        source_document_repo=mock_source_document_repo,
        file_record_repo=mock_file_record_repo,
        status_history_repo=mock_status_history_repo,
        budget_ledger_repo=mock_budget_ledger_repo,
        ai_provider=mock_ai_provider,
        gcs_provider=mock_gcs_provider,
    )


def test_analyze_procurement_no_files_found(analysis_service, caplog):
    """Tests that the analysis is aborted if no files are found for the procurement."""
    mock_procurement = MagicMock(spec=Procurement)
    mock_procurement.pncp_control_number = "123"
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid4()
    analysis_service.procurement_repo.process_procurement_documents.return_value = []

    analysis_service.analyze_procurement(mock_procurement, 1, uuid4())

    assert "No files found for 123. Aborting." in caplog.text


def test_analyze_procurement_no_supported_files(analysis_service, caplog):
    """Tests that the analysis is aborted if no supported files are left after filtering."""
    mock_procurement = MagicMock(spec=Procurement)
    mock_procurement.pncp_control_number = "123"
    analysis_service.procurement_repo.get_procurement_uuid.return_value = uuid4()
    analysis_service.procurement_repo.process_procurement_documents.return_value = [MagicMock()]
    analysis_service.source_document_repo.save_source_document.return_value = uuid4()
    analysis_service._prepare_ai_candidates = MagicMock(
        return_value=[
            MagicMock(
                spec=AIFileCandidate,
                synthetic_id="doc1",
                raw_document_metadata={},
                original_path="test.unsupported",
                original_content=b"test",
                is_included=False,
                exclusion_reason="Unsupported",
                ai_gcs_uris=[],
                prepared_content_gcs_uris=None,
                ai_content=b"test",
                ai_path="test.unsupported",
            )
        ]
    )
    analysis_service._select_files_by_token_limit = MagicMock(return_value=([], []))
    analysis_service.analyze_procurement(mock_procurement, 1, uuid4())
    assert "No supported files left after filtering for 123" in caplog.text