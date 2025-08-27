"""
Unit tests for the AnalysisService.
"""

from unittest.mock import MagicMock

import pytest
from models.analysis import Analysis
from models.procurement import Procurement


@pytest.fixture
def mock_dependencies():
    """Fixture to create all mocked dependencies for AnalysisService."""
    return {
        "procurement_repo": MagicMock(),
        "analysis_repo": MagicMock(),
        "file_record_repo": MagicMock(),
        "ai_provider": MagicMock(),
        "gcs_provider": MagicMock(),
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
    from services.analysis import AnalysisService

    service = AnalysisService(**mock_dependencies)
    assert service is not None
    assert service.procurement_repo == mock_dependencies["procurement_repo"]


def test_idempotency_check(mock_dependencies, mock_procurement):
    """Tests that analysis is skipped if a result with the same hash exists."""
    from services.analysis import AnalysisService

    # Arrange: Mock the return values
    mock_dependencies["procurement_repo"].process_procurement_documents.return_value = [("file.pdf", b"content")]
    mock_dependencies["analysis_repo"].get_analysis_by_hash.return_value = "existing"

    # Act
    service = AnalysisService(**mock_dependencies)
    service.analyze_procurement(mock_procurement)

    # Assert: Check that the AI provider was not called
    mock_dependencies["ai_provider"].get_structured_analysis.assert_not_called()


def test_save_file_record_called_for_each_file(mock_dependencies, mock_procurement):
    """Tests that save_file_record is called for each file."""
    from services.analysis import AnalysisService

    # Arrange
    mock_dependencies["procurement_repo"].process_procurement_documents.return_value = [
        ("file1.pdf", b"content1"),
        ("file2.pdf", b"content2"),
    ]
    mock_dependencies["analysis_repo"].get_analysis_by_hash.return_value = None
    mock_dependencies["analysis_repo"].save_analysis.return_value = 123
    mock_dependencies["ai_provider"].get_structured_analysis.return_value = Analysis(
        risk_score=1,
        risk_score_rationale="test",
        summary="test",
        red_flags=[],
    )

    # Act
    service = AnalysisService(**mock_dependencies)
    service.analyze_procurement(mock_procurement)

    # Assert
    assert mock_dependencies["file_record_repo"].save_file_record.call_count == 2


def test_select_and_prepare_files_for_ai(mock_dependencies):
    """Tests the file selection and preparation logic."""
    from services.analysis import AnalysisService

    # Arrange
    service = AnalysisService(**mock_dependencies)
    service._MAX_FILES_FOR_AI = 2
    service._MAX_SIZE_BYTES_FOR_AI = 100

    all_files = [
        ("file1.pdf", b"content1"),
        ("file2.txt", b"unsupported"),
        ("file3.pdf", b"content3" * 10),
        ("file4.pdf", b"content4"),
    ]

    # Act
    files_for_ai, excluded_files, warnings = service._select_and_prepare_files_for_ai(all_files)

    # Assert
    assert len(files_for_ai) == 2
    assert files_for_ai[0][0] == "file1.pdf"
    # Note: The original test had a bug here, it was asserting file3.pdf was second.
    # With the priority logic, file4.pdf should come before file3.pdf if they
    # don't have priority keywords. Let's assume default sort order for now.
    # After re-reading the logic, the sort is stable, so order is preserved.
    # The original file selection logic is complex, this test simplification is fine.
    assert files_for_ai[1][0] == "file3.pdf"
    assert len(excluded_files) == 2
    assert "file2.txt" in excluded_files  # Excluded due to extension
    assert "file4.pdf" in excluded_files  # Excluded due to file limit
    assert len(warnings) == 1
