"""
Unit tests for the AnalysisService to increase test coverage.
"""

import os
from unittest.mock import MagicMock, patch, call
from uuid import uuid4
from datetime import datetime, timezone, date, timedelta
from typing import Any
from decimal import Decimal

import pytest
from public_detective.constants.analysis_feedback import ExclusionReason
from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.analyses import Analysis, AnalysisResult
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.models.procurements import Procurement
from public_detective.services.analysis import AIFileCandidate, AnalysisService, Modality
from public_detective.repositories.procurements import ProcessedFile


@pytest.fixture
def mock_dependencies() -> dict[str, Any]:
    """Fixture to create mock dependencies for the AnalysisService."""
    return {
        "procurement_repo": MagicMock(),
        "analysis_repo": MagicMock(),
        "source_document_repo": MagicMock(),
        "file_record_repo": MagicMock(),
        "status_history_repo": MagicMock(),
        "budget_ledger_repo": MagicMock(),
        "ai_provider": MagicMock(),
        "gcs_provider": MagicMock(),
        "pubsub_provider": MagicMock(),
    }

@pytest.fixture
def mock_analysis() -> AnalysisResult:
    """Fixture to create a mock analysis object."""
    return AnalysisResult(
        analysis_id=uuid4(),
        procurement_control_number="12345",
        version_number=1,
        status=ProcurementAnalysisStatus.PENDING_ANALYSIS.value,
        updated_at=datetime.now(timezone.utc),
        ai_analysis=Analysis(red_flags=[], seo_keywords=[]),
        analysis_prompt="Test prompt",
        retry_count=0,
        votes_count=1,
        input_tokens_used=100,
        output_tokens_used=50,
        thinking_tokens_used=10,
    )

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


@patch("public_detective.services.analysis.LoggingProvider")
def test_process_analysis_from_message_analysis_not_found(mock_logging_provider, mock_dependencies):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.analysis_repo.get_analysis_by_id.return_value = None

    service.process_analysis_from_message(analysis_id)

    service.analysis_repo.get_analysis_by_id.assert_called_once_with(analysis_id)
    mock_logger.error.assert_called_once_with(f"Analysis with ID {analysis_id} not found.")
    service.procurement_repo.get_procurement_by_id_and_version.assert_not_called()


@patch("public_detective.services.analysis.LoggingProvider")
def test_process_analysis_from_message_procurement_not_found(mock_logging_provider, mock_dependencies, mock_analysis):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)
    analysis_id = mock_analysis.analysis_id
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    service.procurement_repo.get_procurement_by_id_and_version.return_value = None

    service.process_analysis_from_message(analysis_id)

    service.procurement_repo.get_procurement_by_id_and_version.assert_called_once_with(
        mock_analysis.procurement_control_number, mock_analysis.version_number
    )
    mock_logger.error.assert_called_once()
    assert "not found" in mock_logger.error.call_args[0][0]


@patch("public_detective.services.analysis.LoggingProvider")
def test_process_analysis_from_message_main_analysis_fails(mock_logging_provider, mock_dependencies, mock_analysis, mock_procurement):
    mock_logging_provider.return_value.get_logger.return_value = MagicMock()
    service = AnalysisService(**mock_dependencies)
    analysis_id = mock_analysis.analysis_id
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    service.procurement_repo.get_procurement_by_id_and_version.return_value = mock_procurement
    error = Exception("Pipeline failure")
    with patch.object(service, "analyze_procurement", side_effect=error):
        with pytest.raises(AnalysisError) as exc_info:
            service.process_analysis_from_message(analysis_id)

        assert exc_info.value.__cause__ is error

    service.status_history_repo.create_record.assert_called_with(
        analysis_id, ProcurementAnalysisStatus.ANALYSIS_FAILED, str(error)
    )


@patch("public_detective.services.analysis.LoggingProvider")
def test_process_analysis_from_message_outer_exception(mock_logging_provider, mock_dependencies):
    mock_logging_provider.return_value.get_logger.return_value = MagicMock()
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    error = Exception("Unexpected error")
    service.analysis_repo.get_analysis_by_id.side_effect = error

    with pytest.raises(AnalysisError) as exc_info:
        service.process_analysis_from_message(analysis_id)

    assert "Failed to process analysis from message" in str(exc_info.value)
    assert exc_info.value.__cause__ is error


@patch("public_detective.services.analysis.LoggingProvider")
def test_run_specific_analysis_not_found(mock_logging_provider, mock_dependencies):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.analysis_repo.get_analysis_by_id.return_value = None

    service.run_specific_analysis(analysis_id)

    mock_logger.error.assert_called_once_with(f"Analysis with ID {analysis_id} not found.")
    service.pubsub_provider.publish.assert_not_called()


@patch("public_detective.services.analysis.LoggingProvider")
def test_run_specific_analysis_wrong_status(mock_logging_provider, mock_dependencies, mock_analysis):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)
    mock_analysis.status = ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis

    service.run_specific_analysis(mock_analysis.analysis_id)

    mock_logger.warning.assert_called_once()
    assert "not in PENDING_ANALYSIS state" in mock_logger.warning.call_args[0][0]
    service.pubsub_provider.publish.assert_not_called()


@patch("public_detective.services.analysis.LoggingProvider")
def test_run_specific_analysis_no_pubsub(mock_logging_provider, mock_dependencies, mock_analysis):
    mock_logging_provider.return_value.get_logger.return_value = MagicMock()
    mock_dependencies["pubsub_provider"] = None
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis

    with pytest.raises(AnalysisError) as exc_info:
        service.run_specific_analysis(mock_analysis.analysis_id)

    assert isinstance(exc_info.value.__cause__, ValueError)
    assert "PubSubProvider is not configured" in str(exc_info.value.__cause__)


@patch("public_detective.services.analysis.LoggingProvider")
def test_run_specific_analysis_outer_exception(mock_logging_provider, mock_dependencies):
    mock_logging_provider.return_value.get_logger.return_value = MagicMock()
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    error = Exception("Unexpected repo error")
    service.analysis_repo.get_analysis_by_id.side_effect = error

    with pytest.raises(AnalysisError) as exc_info:
        service.run_specific_analysis(analysis_id)

    assert "An unexpected error occurred during specific analysis" in str(exc_info.value)
    assert exc_info.value.__cause__ is error


@patch("public_detective.services.analysis.LoggingProvider")
def test_get_procurement_overall_status_found(mock_logging_provider, mock_dependencies):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)
    control_number = "PNCP123"
    expected_status = {"status": "ANALYSIS_SUCCESSFUL", "version": 1}
    service.analysis_repo.get_procurement_overall_status.return_value = expected_status

    result = service.get_procurement_overall_status(control_number)

    assert result == expected_status
    service.analysis_repo.get_procurement_overall_status.assert_called_once_with(control_number)
    mock_logger.info.assert_called_once_with(f"Fetching overall status for procurement {control_number}.")


@patch("public_detective.services.analysis.LoggingProvider")
def test_get_procurement_overall_status_not_found(mock_logging_provider, mock_dependencies):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)
    control_number = "PNCP123"
    service.analysis_repo.get_procurement_overall_status.return_value = None

    result = service.get_procurement_overall_status(control_number)

    assert result is None
    mock_logger.warning.assert_called_once_with(f"No overall status found for procurement {control_number}.")

@patch("public_detective.services.analysis.LoggingProvider")
def test_get_modality(mock_logging_provider, mock_dependencies):
    service = AnalysisService(**mock_dependencies)

    text_candidate = AIFileCandidate(original_path="doc.pdf", original_content=b"", synthetic_id="1", raw_document_metadata={})
    image_candidate = AIFileCandidate(original_path="image.jpg", original_content=b"", synthetic_id="2", raw_document_metadata={})
    audio_candidate = AIFileCandidate(original_path="audio.mp3", original_content=b"", synthetic_id="3", raw_document_metadata={})
    video_candidate = AIFileCandidate(original_path="video.mp4", original_content=b"", synthetic_id="4", raw_document_metadata={})

    assert service._get_modality([text_candidate]) == Modality.TEXT
    assert service._get_modality([text_candidate, image_candidate]) == Modality.IMAGE
    assert service._get_modality([text_candidate, audio_candidate]) == Modality.AUDIO
    assert service._get_modality([text_candidate, video_candidate]) == Modality.VIDEO
    assert service._get_modality([image_candidate, video_candidate]) == Modality.VIDEO

@patch("public_detective.services.analysis.LoggingProvider")
def test_prepare_ai_candidates_conversion_failure(mock_logging_provider, mock_dependencies):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)

    processed_file = ProcessedFile(
        source_document_id=str(uuid4()),
        raw_document_metadata={"titulo": "Edital"},
        relative_path="file.docx",
        content=b"content",
    )

    service.converter_service.docx_to_html = MagicMock(side_effect=Exception("Conversion failed"))

    candidates = service._prepare_ai_candidates([processed_file])

    assert len(candidates) == 1
    assert candidates[0].exclusion_reason is not None
    assert candidates[0].exclusion_reason == ExclusionReason.CONVERSION_FAILED
    mock_logger.error.assert_called_once()

@patch("public_detective.services.analysis.LoggingProvider")
def test_analyze_procurement_no_procurement_id(mock_logging_provider, mock_dependencies, mock_procurement):
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_procurement_uuid.return_value = None

    with pytest.raises(AnalysisError, match="Could not find procurement UUID"):
        service.analyze_procurement(mock_procurement, 1, uuid4())

@patch("public_detective.services.analysis.LoggingProvider")
def test_calculate_auto_budget_invalid_period(mock_logging_provider, mock_dependencies):
    service = AnalysisService(**mock_dependencies)
    with pytest.raises(ValueError, match="Invalid budget period: invalid"):
        service._calculate_auto_budget("invalid")

@patch("public_detective.services.analysis.datetime")
@patch("public_detective.services.analysis.LoggingProvider")
def test_calculate_auto_budget(mock_logging_provider, mock_datetime, mock_dependencies):
    mock_datetime.now.return_value = datetime(2025, 7, 15, tzinfo=timezone.utc)

    service = AnalysisService(**mock_dependencies)

    current_balance = Decimal("1000")
    expenses_in_period = Decimal("100")
    service.budget_ledger_repo.get_total_donations.return_value = current_balance
    service.budget_ledger_repo.get_total_expenses_for_period.return_value = expenses_in_period

    budget = service._calculate_auto_budget("daily")
    assert budget == Decimal("1000")

    budget = service._calculate_auto_budget("weekly")
    assert round(budget, 4) == Decimal("214.2857")

    budget = service._calculate_auto_budget("monthly")
    assert round(budget, 4) == Decimal("432.2581")

@patch("public_detective.services.analysis.LoggingProvider")
def test_run_pre_analysis_happy_path(mock_logging_provider, mock_dependencies, mock_procurement):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)

    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = [(mock_procurement, {})]
    with patch.object(service, "_pre_analyze_procurement") as mock_pre_analyze:
        service.run_pre_analysis(date(2025, 1, 1), date(2025, 1, 1), 10, 0)
        mock_pre_analyze.assert_called_once_with(mock_procurement, {})

@patch("public_detective.services.analysis.LoggingProvider")
def test_run_pre_analysis_no_procurements(mock_logging_provider, mock_dependencies):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_updated_procurements_with_raw_data.return_value = []

    with patch.object(service, "_pre_analyze_procurement") as mock_pre_analyze:
        service.run_pre_analysis(date(2025, 1, 1), date(2025, 1, 1), 10, 0)
        mock_pre_analyze.assert_not_called()
    assert mock_logger.info.call_count == 4

@patch("public_detective.services.analysis.LoggingProvider")
def test_pre_analyze_procurement_hash_exists(mock_logging_provider, mock_dependencies, mock_procurement):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)
    service.procurement_repo.get_procurement_by_hash.return_value = "some_hash"

    with patch("hashlib.sha256") as mock_sha:
        mock_sha.return_value.hexdigest.return_value = "some_hash"
        service._pre_analyze_procurement(mock_procurement, {})

    service.procurement_repo.save_procurement_version.assert_not_called()
    mock_logger.info.assert_any_call("Procurement with hash some_hash already exists. Skipping.")

@patch("public_detective.services.analysis.LoggingProvider")
def test_run_ranked_analysis_manual_budget(mock_logging_provider, mock_dependencies, mock_analysis):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)

    mock_analysis.total_cost = Decimal("50")
    service.analysis_repo.get_pending_analyses_ranked.return_value = [mock_analysis]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        service.run_ranked_analysis(False, None, 10, budget=Decimal("100"))
        mock_run_specific.assert_called_once_with(mock_analysis.analysis_id)

@patch("public_detective.services.analysis.LoggingProvider")
def test_run_ranked_analysis_auto_budget(mock_logging_provider, mock_dependencies, mock_analysis):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)

    mock_analysis.total_cost = Decimal("50")
    service.analysis_repo.get_pending_analyses_ranked.return_value = [mock_analysis]

    with patch.object(service, "_calculate_auto_budget", return_value=Decimal("100")) as mock_calc_budget:
        with patch.object(service, "run_specific_analysis") as mock_run_specific:
            service.run_ranked_analysis(True, "daily", 10)
            mock_calc_budget.assert_called_once_with("daily")
            mock_run_specific.assert_called_once_with(mock_analysis.analysis_id)

@patch("public_detective.services.analysis.LoggingProvider")
def test_run_ranked_analysis_no_budget(mock_logging_provider, mock_dependencies):
    service = AnalysisService(**mock_dependencies)
    with pytest.raises(ValueError, match="Either a manual budget must be provided or auto-budget must be enabled."):
        service.run_ranked_analysis(False, None, 10)

@patch("public_detective.services.analysis.LoggingProvider")
def test_run_ranked_analysis_budget_exceeded(mock_logging_provider, mock_dependencies, mock_analysis):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)

    mock_analysis.total_cost = Decimal("150")
    service.analysis_repo.get_pending_analyses_ranked.return_value = [mock_analysis]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        service.run_ranked_analysis(False, None, 10, budget=Decimal("100"))
        mock_run_specific.assert_not_called()
    mock_logger.info.assert_any_call(f"Skipping analysis {mock_analysis.analysis_id}. Cost (150.00 BRL) exceeds remaining budget (100.00 BRL).")

@patch("public_detective.services.analysis.LoggingProvider")
def test_run_ranked_analysis_max_messages(mock_logging_provider, mock_dependencies, mock_analysis):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)

    analysis1 = mock_analysis
    analysis2 = mock_analysis
    analysis1.total_cost = Decimal("10")
    analysis2.total_cost = Decimal("10")
    service.analysis_repo.get_pending_analyses_ranked.return_value = [analysis1, analysis2]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        service.run_ranked_analysis(False, None, 10, budget=Decimal("100"), max_messages=1)
        mock_run_specific.assert_called_once()
    mock_logger.info.assert_any_call("Reached max_messages limit of 1. Stopping job.")

@patch("public_detective.services.analysis.LoggingProvider")
def test_retry_analyses_happy_path(mock_logging_provider, mock_dependencies, mock_analysis):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)

    mock_analysis.updated_at = datetime.now(timezone.utc) - timedelta(hours=2)
    service.analysis_repo.get_analyses_to_retry.return_value = [mock_analysis]
    service.analysis_repo.save_retry_analysis.return_value = uuid4()

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        count = service.retry_analyses(1, 3, 24)
        assert count == 1
        mock_run_specific.assert_called_once()

@patch("public_detective.services.analysis.LoggingProvider")
def test_retry_analyses_backoff(mock_logging_provider, mock_dependencies, mock_analysis):
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    service = AnalysisService(**mock_dependencies)

    mock_analysis.updated_at = datetime.now(timezone.utc)
    service.analysis_repo.get_analyses_to_retry.return_value = [mock_analysis]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        count = service.retry_analyses(1, 3, 24)
        assert count == 0
        mock_run_specific.assert_not_called()

@patch("public_detective.services.analysis.LoggingProvider")
def test_retry_analyses_exception(mock_logging_provider, mock_dependencies):
    service = AnalysisService(**mock_dependencies)
    error = Exception("DB error")
    service.analysis_repo.get_analyses_to_retry.side_effect = error

    with pytest.raises(AnalysisError) as exc_info:
        service.retry_analyses(1, 3, 24)
    assert exc_info.value.__cause__ is error