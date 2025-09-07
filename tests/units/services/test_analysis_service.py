import hashlib
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from exceptions.analysis import AnalysisError
from services.analysis import AnalysisService


@pytest.fixture
def mock_dependencies() -> dict:
    """Fixture to create all mocked dependencies for AnalysisService.

    Returns:
        A dictionary of mocked dependencies.
    """
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


def test_calculate_hash(mock_dependencies: dict) -> None:
    """
    Tests that _calculate_hash returns the correct SHA-256 hash.
    """
    service = AnalysisService(**mock_dependencies)
    files = [("file1.txt", b"content1"), ("file2.txt", b"content2")]
    expected_hash = hashlib.sha256(b"content1" + b"content2").hexdigest()

    actual_hash = service._calculate_hash(files)

    assert actual_hash == expected_hash


def test_get_priority(mock_dependencies: dict) -> None:
    """
    Tests that _get_priority returns the correct priority for a file.
    """
    service = AnalysisService(**mock_dependencies)
    assert service._get_priority("edital.pdf") == 0
    assert service._get_priority("termo de referencia.docx") == 1
    assert service._get_priority("outro_arquivo.pdf") == len(service._FILE_PRIORITY_ORDER)


def test_get_priority_as_string(mock_dependencies: dict) -> None:
    """
    Tests that _get_priority_as_string returns the correct priority string.
    """
    service = AnalysisService(**mock_dependencies)
    assert "edital" in service._get_priority_as_string("edital.pdf")
    assert "termo de referencia" in service._get_priority_as_string("termo de referencia.docx")
    assert "Sem priorização" in service._get_priority_as_string("outro_arquivo.pdf")


def test_calculate_estimated_cost(mock_dependencies: dict) -> None:
    """
    Tests that _calculate_estimated_cost returns the correct cost.
    """
    service = AnalysisService(**mock_dependencies)
    # Using the service's pricing constants for the calculation
    input_price = service._GEMINI_PRO_INPUT_PRICE_PER_MILLION_TOKENS
    output_price = service._GEMINI_PRO_OUTPUT_PRICE_PER_MILLION_TOKENS

    input_tokens = 500000  # 0.5 million
    output_tokens = 250000  # 0.25 million

    expected_cost = (Decimal(input_tokens) / 1_000_000) * input_price + (
        Decimal(output_tokens) / 1_000_000
    ) * output_price

    actual_cost = service._calculate_estimated_cost(input_tokens, output_tokens)

    assert actual_cost == expected_cost


def test_build_analysis_prompt(mock_dependencies: dict) -> None:
    """
    Tests that _build_analysis_prompt constructs the correct prompt.
    """
    from models.procurements import Procurement

    service = AnalysisService(**mock_dependencies)
    procurement_data = {
        "processo": "123",
        "objetoCompra": "Test Object",
        "amparoLegal": {"codigo": 1, "nome": "Test Law", "descricao": "Desc"},
        "srp": False,
        "orgaoEntidade": {"cnpj": "12345678000199", "razaoSocial": "Test Org", "poderId": "E", "esferaId": "F"},
        "anoCompra": 2025,
        "sequencialCompra": 1,
        "dataPublicacaoPncp": "2025-01-01T12:00:00",
        "dataAtualizacao": "2025-01-01T12:00:00",
        "numeroCompra": "1/2025",
        "unidadeOrgao": {
            "ufNome": "Test State",
            "codigoUnidade": "123",
            "nomeUnidade": "Test Unit",
            "ufSigla": "TS",
            "municipioNome": "Test City",
            "codigoIbge": "12345",
        },
        "modalidadeId": 1,
        "numeroControlePNCP": "PNCP-123",
        "dataAtualizacaoGlobal": "2025-01-01T12:00:00",
        "modoDisputaId": 1,
        "situacaoCompraId": 1,
        "usuarioNome": "Test User",
    }
    procurement = Procurement.model_validate(procurement_data)
    warnings = ["Warning 1", "Warning 2"]

    prompt = service._build_analysis_prompt(procurement, warnings)

    assert "METADADOS DA LICITAÇÃO (JSON)" in prompt
    assert "Warning 1" in prompt
    assert "Warning 2" in prompt
    assert procurement.object_description in prompt


def test_select_and_prepare_files_for_ai(mock_dependencies: dict) -> None:
    """
    Tests the file selection and preparation logic.
    """
    service = AnalysisService(**mock_dependencies)
    all_files = [
        ("edital.pdf", b"content1"),
        ("termo de referencia.docx", b"content2"),
        ("anexo.unsupported", b"content3"),
        ("planilha.xlsx", b"content4" * (1024 * 1024)),  # 8MB file
        ("orcamento.csv", b"content5"),
    ]

    # Temporarily reduce size limit for testing
    service._MAX_SIZE_BYTES_FOR_AI = 5 * 1024 * 1024

    final_files, excluded_files, warnings = service._select_and_prepare_files_for_ai(all_files)

    assert len(final_files) == 3
    assert final_files[0][0] == "edital.pdf"
    assert final_files[1][0] == "termo de referencia.docx"
    assert final_files[2][0] == "orcamento.csv"

    assert "anexo.unsupported" in excluded_files
    assert "planilha.xlsx" in excluded_files

    assert len(warnings) == 1
    assert "excedido" in warnings[0]


def test_run_specific_analysis_success(mock_dependencies: dict) -> None:
    """
    Tests that run_specific_analysis triggers an analysis successfully.
    """
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    analysis_result = MagicMock()
    analysis_result.status = "PENDING_ANALYSIS"
    analysis_result.procurement_control_number = "PNCP-123"
    analysis_result.version_number = 1
    service.analysis_repo.get_analysis_by_id.return_value = analysis_result

    service.run_specific_analysis(analysis_id)

    service.pubsub_provider.publish.assert_called_once()
    service.analysis_repo.update_analysis_status.assert_called_once()


def test_run_specific_analysis_not_found(mock_dependencies: dict) -> None:
    """
    Tests that run_specific_analysis does nothing if the analysis is not found.
    """
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.analysis_repo.get_analysis_by_id.return_value = None

    service.run_specific_analysis(analysis_id)

    service.pubsub_provider.publish.assert_not_called()


def test_run_specific_analysis_not_pending(mock_dependencies: dict) -> None:
    """
    Tests that run_specific_analysis does nothing if the analysis is not pending.
    """
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    analysis_result = MagicMock()
    analysis_result.status = "ANALYSIS_SUCCESSFUL"
    service.analysis_repo.get_analysis_by_id.return_value = analysis_result

    service.run_specific_analysis(analysis_id)

    service.pubsub_provider.publish.assert_not_called()


def test_run_specific_analysis_no_pubsub(mock_dependencies: dict) -> None:
    """
    Tests that run_specific_analysis raises an error if pubsub is not configured.
    """
    service = AnalysisService(**mock_dependencies)
    service.pubsub_provider = None
    analysis_id = uuid4()
    analysis_result = MagicMock()
    analysis_result.status = "PENDING_ANALYSIS"
    service.analysis_repo.get_analysis_by_id.return_value = analysis_result

    with pytest.raises(AnalysisError):
        service.run_specific_analysis(analysis_id)


def test_analyze_procurement_reuse_existing(mock_dependencies: dict) -> None:
    """
    Tests that analyze_procurement reuses an existing analysis.
    """
    from models.analyses import Analysis, AnalysisResult

    service = AnalysisService(**mock_dependencies)
    procurement = MagicMock()
    procurement.pncp_control_number = "PNCP-123"
    analysis_id = uuid4()
    existing_analysis = AnalysisResult(
        procurement_control_number="PNCP-123",
        version_number=1,
        document_hash="hash123",
        ai_analysis=Analysis(
            risk_score=5,
            risk_score_rationale="Rationale",
            procurement_summary="Summary",
            analysis_summary="Summary",
            red_flags=[],
        ),
        warnings=[],
        original_documents_gcs_path="",
        processed_documents_gcs_path="",
    )
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    service.analysis_repo.get_analysis_by_hash.return_value = existing_analysis

    service.analyze_procurement(procurement, 1, analysis_id)

    service.analysis_repo.save_analysis.assert_called_once()
    service.file_record_repo.save_file_record.assert_called_once()


def test_analyze_procurement_success(mock_dependencies: dict) -> None:
    """
    Tests the successful analysis of a procurement.
    """
    from models.analyses import Analysis

    service = AnalysisService(**mock_dependencies)
    procurement = MagicMock()
    procurement.pncp_control_number = "PNCP-123"
    analysis_id = uuid4()
    ai_analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Rationale",
        procurement_summary="Summary",
        analysis_summary="Summary",
        red_flags=[],
    )
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    service.analysis_repo.get_analysis_by_hash.return_value = None
    service.ai_provider.get_structured_analysis.return_value = (ai_analysis, 100, 50)

    service.analyze_procurement(procurement, 1, analysis_id)

    service.analysis_repo.save_analysis.assert_called_once()
    service.gcs_provider.upload_file.assert_called()
    service.file_record_repo.save_file_record.assert_called()


def test_process_analysis_from_message_success(mock_dependencies: dict) -> None:
    """
    Tests the successful processing of an analysis from a message.
    """
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    analysis_result = MagicMock()
    procurement = MagicMock()
    service.analysis_repo.get_analysis_by_id.return_value = analysis_result
    service.procurement_repo.get_procurement_by_id_and_version.return_value = procurement

    with patch.object(service, "analyze_procurement") as mock_analyze_procurement:
        service.process_analysis_from_message(analysis_id)
        mock_analyze_procurement.assert_called_once_with(procurement, analysis_result.version_number, analysis_id, None)
        service.analysis_repo.update_analysis_status.assert_called()


def test_run_ranked_analysis_manual_budget(mock_dependencies: dict) -> None:
    """
    Tests the ranked analysis with a manual budget.
    """
    from models.analyses import AnalysisResult

    service = AnalysisService(**mock_dependencies)
    analysis1 = MagicMock(spec=AnalysisResult)
    analysis1.analysis_id = uuid4()
    analysis1.votes_count = 10
    analysis1.input_tokens_used = 1000
    analysis1.output_tokens_used = 500
    analysis1.procurement_control_number = "PNCP-1"
    analysis1.version_number = 1

    analysis2 = MagicMock(spec=AnalysisResult)
    analysis2.analysis_id = uuid4()
    analysis2.votes_count = 5
    analysis2.input_tokens_used = 2000
    analysis2.output_tokens_used = 1000
    analysis2.procurement_control_number = "PNCP-2"
    analysis2.version_number = 1

    service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis1, analysis2]
    with patch.object(service, "_calculate_estimated_cost", return_value=Decimal("1.00")), patch.object(
        service, "run_specific_analysis"
    ) as mock_run_specific:
        service.run_ranked_analysis(use_auto_budget=False, budget=Decimal("1.50"), budget_period=None, zero_vote_budget_percent=10)

    assert mock_run_specific.call_count == 1


def test_run_ranked_analysis_budget_exhausted(mock_dependencies: dict) -> None:
    """
    Tests that the ranked analysis stops when the budget is exhausted.
    """
    from models.analyses import AnalysisResult

    service = AnalysisService(**mock_dependencies)
    analysis1 = MagicMock(spec=AnalysisResult)
    analysis1.analysis_id = uuid4()
    analysis1.votes_count = 10
    analysis1.input_tokens_used = 1000
    analysis1.output_tokens_used = 500
    analysis1.procurement_control_number = "PNCP-1"
    analysis1.version_number = 1

    service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis1]
    with patch.object(service, "_calculate_estimated_cost", return_value=Decimal("2.00")), patch.object(
        service, "run_specific_analysis"
    ) as mock_run_specific:
        service.run_ranked_analysis(use_auto_budget=False, budget=Decimal("1.50"), budget_period=None, zero_vote_budget_percent=10)

    mock_run_specific.assert_not_called()


def test_run_ranked_analysis_max_messages(mock_dependencies: dict) -> None:
    """
    Tests that the ranked analysis stops when the max_messages limit is reached.
    """
    from models.analyses import AnalysisResult

    service = AnalysisService(**mock_dependencies)
    analysis1 = MagicMock(spec=AnalysisResult)
    analysis1.analysis_id = uuid4()
    analysis1.votes_count = 10
    analysis1.input_tokens_used = 1000
    analysis1.output_tokens_used = 500
    analysis1.procurement_control_number = "PNCP-1"
    analysis1.version_number = 1

    service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis1]
    with patch.object(service, "_calculate_estimated_cost", return_value=Decimal("1.00")), patch.object(
        service, "run_specific_analysis"
    ) as mock_run_specific:
        service.run_ranked_analysis(
            use_auto_budget=False, budget=Decimal("1.50"), budget_period=None, zero_vote_budget_percent=10, max_messages=0
        )

    mock_run_specific.assert_not_called()


def test_run_ranked_analysis_zero_vote_budget(mock_dependencies: dict) -> None:
    """
    Tests that a zero-vote analysis is skipped if it exceeds the zero-vote budget.
    """
    from models.analyses import AnalysisResult

    service = AnalysisService(**mock_dependencies)
    analysis1 = MagicMock(spec=AnalysisResult)
    analysis1.analysis_id = uuid4()
    analysis1.votes_count = 0
    analysis1.input_tokens_used = 1000
    analysis1.output_tokens_used = 500
    analysis1.procurement_control_number = "PNCP-1"
    analysis1.version_number = 1

    service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis1]
    with patch.object(service, "_calculate_estimated_cost", return_value=Decimal("1.00")), patch.object(
        service, "run_specific_analysis"
    ) as mock_run_specific:
        service.run_ranked_analysis(use_auto_budget=False, budget=Decimal("1.50"), budget_period=None, zero_vote_budget_percent=10)

    mock_run_specific.assert_not_called()


def test_run_ranked_analysis_auto_budget(mock_dependencies: dict) -> None:
    """
    Tests the ranked analysis with auto-budget.
    """
    service = AnalysisService(**mock_dependencies)
    with patch.object(service, "_calculate_auto_budget", return_value=Decimal("10.00")):
        service.run_ranked_analysis(use_auto_budget=True, budget_period="daily", zero_vote_budget_percent=10)
        service._calculate_auto_budget.assert_called_once_with("daily")


def test_calculate_auto_budget(mock_dependencies: dict) -> None:
    """
    Tests the auto-budget calculation.
    """
    service = AnalysisService(**mock_dependencies)
    service.budget_ledger_repo.get_total_donations.return_value = Decimal("1000")
    service.budget_ledger_repo.get_total_expenses_for_period.return_value = Decimal("100")

    with patch("services.analysis.datetime") as mock_datetime:
        mock_date = MagicMock(spec=date)
        mock_date.weekday.return_value = 2  # Wednesday
        mock_date.day = 15
        mock_date.replace.return_value = date(2025, 3, 1)
        mock_datetime.now.return_value.date.return_value = mock_date

        budget = service._calculate_auto_budget("weekly")
        assert budget > 0

        budget = service._calculate_auto_budget("daily")
        assert budget > 0

        budget = service._calculate_auto_budget("monthly")
        assert budget > 0

    # Test negative budget case
    service.budget_ledger_repo.get_total_expenses_for_period.return_value = Decimal("1000")
    with patch("services.analysis.datetime") as mock_datetime:
        mock_date = MagicMock(spec=date)
        mock_date.weekday.return_value = 0  # Monday
        mock_date.day = 17
        mock_datetime.now.return_value.date.return_value = mock_date
        budget = service._calculate_auto_budget("weekly")
        assert budget == 0

    with pytest.raises(ValueError):
        service._calculate_auto_budget("invalid_period")


def test_get_procurement_overall_status(mock_dependencies: dict) -> None:
    """
    Tests retrieving the overall status of a procurement.
    """
    service = AnalysisService(**mock_dependencies)
    control_number = "PNCP-123"
    status_info = {"status": "ANALYZED_CURRENT"}
    service.analysis_repo.get_procurement_overall_status.return_value = status_info

    result = service.get_procurement_overall_status(control_number)

    assert result == status_info
    service.analysis_repo.get_procurement_overall_status.assert_called_once_with(control_number)


def test_get_procurement_overall_status_not_found(mock_dependencies: dict) -> None:
    """
    Tests retrieving the overall status when no analysis is found.
    """
    service = AnalysisService(**mock_dependencies)
    control_number = "PNCP-123"
    service.analysis_repo.get_procurement_overall_status.return_value = None

    result = service.get_procurement_overall_status(control_number)

    assert result is None
