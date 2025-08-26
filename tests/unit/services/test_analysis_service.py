"""
Unit tests for the AnalysisService.
"""

from unittest.mock import MagicMock, patch

from models.procurement import Procurement


@patch("services.analysis.FileRecordRepository")
@patch("services.analysis.AnalysisRepository")
@patch("services.analysis.ProcurementRepository")
@patch("services.analysis.GcsProvider")
@patch("services.analysis.AiProvider")
@patch("providers.config.ConfigProvider.get_config")
def test_analysis_service_instantiation(
    mock_get_config, _mock_ai, _mock_gcs, _mock_proc_repo, _mock_analysis_repo, _mock_file_repo
):
    """Tests that the AnalysisService can be instantiated correctly."""
    from services.analysis import AnalysisService

    mock_config = MagicMock()
    mock_config.GCP_GEMINI_API_KEY = "test-key"
    mock_get_config.return_value = mock_config

    service = AnalysisService()
    assert service is not None


@patch("services.analysis.FileRecordRepository")
@patch("services.analysis.AnalysisRepository")
@patch("services.analysis.ProcurementRepository")
@patch("services.analysis.GcsProvider")
@patch("services.analysis.AiProvider")
def test_idempotency_check(
    _mock_ai_provider,
    _mock_gcs_provider,
    mock_procurement_repo,
    mock_analysis_repo,
    _mock_file_record_repo,
):
    """Tests that analysis is skipped if a result with the same hash exists."""
    from services.analysis import AnalysisService

    mock_procurement_repo.return_value.process_procurement_documents.return_value = [("file.pdf", b"content")]
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


@patch("services.analysis.FileRecordRepository")
@patch("services.analysis.AnalysisRepository")
@patch("services.analysis.ProcurementRepository")
@patch("services.analysis.GcsProvider")
@patch("services.analysis.AiProvider")
def test_save_file_record_called_for_each_file(
    mock_ai_provider,
    _mock_gcs_provider,
    mock_procurement_repo,
    mock_analysis_repo,
    mock_file_record_repo,
):
    """Tests that save_file_record is called for each file."""
    from services.analysis import AnalysisService

    mock_procurement_repo.return_value.process_procurement_documents.return_value = [
        ("file1.pdf", b"content1"),
        ("file2.pdf", b"content2"),
    ]
    mock_analysis_repo.return_value.get_analysis_by_hash.return_value = None
    mock_analysis_repo.return_value.save_analysis.return_value = 123
    from models.analysis import Analysis

    mock_ai_provider.return_value.get_structured_analysis.return_value = Analysis(
        risk_score=1,
        risk_score_rationale="test",
        summary="test",
        red_flags=[],
    )

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

    assert mock_file_record_repo.return_value.save_file_record.call_count == 2


@patch("services.analysis.FileRecordRepository")
@patch("services.analysis.AnalysisRepository")
@patch("services.analysis.ProcurementRepository")
@patch("services.analysis.GcsProvider")
@patch("services.analysis.AiProvider")
def test_select_and_prepare_files_for_ai(
    _mock_ai_provider,
    _mock_gcs_provider,
    _mock_procurement_repo,
    _mock_analysis_repo,
    _mock_file_record_repo,
):
    """Tests the file selection and preparation logic."""
    from services.analysis import AnalysisService

    service = AnalysisService()
    service._MAX_FILES_FOR_AI = 2
    service._MAX_SIZE_BYTES_FOR_AI = 100

    all_files = [
        ("file1.pdf", b"content1"),
        ("file2.txt", b"unsupported"),
        ("file3.pdf", b"content3" * 10),
        ("file4.pdf", b"content4"),
    ]

    files_for_ai, excluded_files, warnings = service._select_and_prepare_files_for_ai(all_files)

    assert len(files_for_ai) == 2
    assert files_for_ai[0][0] == "file1.pdf"
    assert files_for_ai[1][0] == "file3.pdf"
    assert len(excluded_files) == 2
    assert "file2.txt" in excluded_files
    assert "file4.pdf" in excluded_files
    assert len(warnings) == 1
