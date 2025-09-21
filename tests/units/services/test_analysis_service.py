"""This module contains the unit tests for the AnalysisService."""

from datetime import date, datetime
from decimal import Decimal
from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from public_detective.exceptions.analysis import AnalysisError
from public_detective.models.analyses import Analysis
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.models.procurements import Procurement
from public_detective.services.analysis import AnalysisService


@pytest.fixture
def mock_dependencies() -> dict[str, Any]:
    """Fixture to create all mocked dependencies for AnalysisService."""
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


def test_calculate_hash(mock_dependencies: dict[str, Any]) -> None:
    """Test that the _calculate_hash method returns the correct hash."""
    service = AnalysisService(**mock_dependencies)
    files = [("file1.txt", b"hello"), ("file2.txt", b"world")]
    # The expected hash is the sha256 of "helloworld"
    expected_hash = "936a185caaa266bb9cbe981e9e05cb78cd732b0b3280eb944412bb6f8f8f07af"
    assert service._calculate_hash(files) == expected_hash


def test_get_priority(mock_dependencies: dict[str, Any]) -> None:
    """Test that the _get_priority method returns the correct priority."""
    service = AnalysisService(**mock_dependencies)
    assert service._get_priority("edital.pdf") == 0
    assert service._get_priority("termo de referencia.docx") == 1
    assert service._get_priority("some_other_file.pdf") == len(service._FILE_PRIORITY_ORDER)


def test_get_priority_as_string(mock_dependencies: dict[str, Any]) -> None:
    """Test that the _get_priority_as_string method returns the correct string."""
    service = AnalysisService(**mock_dependencies)
    assert "edital" in service._get_priority_as_string("edital.pdf")
    assert "termo de referencia" in service._get_priority_as_string("termo de referencia.docx")
    assert "Sem priorização." in service._get_priority_as_string("some_other_file.pdf")


def test_update_status_with_history(mock_dependencies: dict[str, Any]) -> None:
    """Test that the _update_status_with_history method calls the correct repositories."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    status = "ANALYSIS_SUCCESSFUL"
    details = "Details"

    service._update_status_with_history(analysis_id, status, details)

    service.analysis_repo.update_analysis_status.assert_called_once_with(analysis_id, status)
    service.status_history_repo.create_record.assert_called_once_with(analysis_id, status, details)


def test_build_analysis_prompt(mock_dependencies: dict[str, Any], mock_procurement: Procurement) -> None:
    """Test that the _build_analysis_prompt method constructs the correct prompt."""
    service = AnalysisService(**mock_dependencies)
    warnings = ["Warning 1", "Warning 2"]
    prompt = service._build_analysis_prompt(mock_procurement, warnings)

    assert "Você é um auditor sênior" in prompt
    assert "Warning 1" in prompt
    assert "Warning 2" in prompt
    assert mock_procurement.model_dump_json(by_alias=True, indent=2) in prompt


def test_select_and_prepare_files_for_ai_happy_path(
    mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test the happy path for _select_and_prepare_files_for_ai."""
    service = AnalysisService(**mock_dependencies)
    files = [("file1.pdf", b"content1"), ("file2.docx", b"content2")]
    service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)

    selected_files, excluded_files, warnings, tokens = service._select_and_prepare_files_for_ai(files, mock_procurement)

    assert len(selected_files) == 2
    assert not excluded_files
    assert not warnings  # No warning message for ignored files
    assert tokens > 0


def test_select_and_prepare_files_for_ai_unsupported_extension(
    mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test that files with unsupported extensions are excluded."""
    service = AnalysisService(**mock_dependencies)
    files = [("file1.txt", b"content1"), ("file2.pdf", b"content2")]
    service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)

    selected_files, excluded_files, warnings, tokens = service._select_and_prepare_files_for_ai(files, mock_procurement)

    assert len(selected_files) == 1
    assert selected_files[0][0] == "file2.pdf"
    assert len(excluded_files) == 1
    assert "file1.txt" in excluded_files


def test_select_and_prepare_files_for_ai_token_limit_exceeded(
    mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test that files are excluded when the token limit is exceeded."""
    service = AnalysisService(**mock_dependencies)
    service.config.GCP_GEMINI_MAX_INPUT_TOKENS = 100
    # Prioritized file first
    files = [("edital.pdf", b"content1"), ("anexo.pdf", b"content2")]

    def count_tokens_side_effect(prompt: str, files: list) -> tuple[int, int, int]:
        # Base prompt with warning for both files
        if "edital.pdf" in prompt and "anexo.pdf" in prompt:
            return (30, 0, 0)
        # Base prompt with warning for one file
        if "anexo.pdf" in prompt:
            return (20, 0, 0)
        # Final calculation with selected files
        if files:
            # If it's the check for the second file, make it exceed the limit
            if len(files) > 1:
                return (110, 0, 0)
            # The prompt will have a warning for the second file
            if "anexo.pdf" in prompt:
                return (20 + 50, 0, 0)  # warning + file1
        # Token count for a single file
        if files and "edital" in files[0][0]:
            return (50, 0, 0)
        if files and "anexo" in files[0][0]:
            return (70, 0, 0)  # This one is larger
        # Base prompt
        return (10, 0, 0)

    service.ai_provider.count_tokens_for_analysis.side_effect = count_tokens_side_effect

    selected_files, excluded_files, warnings, tokens = service._select_and_prepare_files_for_ai(files, mock_procurement)

    assert len(selected_files) == 1
    assert selected_files[0][0] == "edital.pdf"
    assert len(excluded_files) == 1
    assert "anexo.pdf" in excluded_files
    assert len(warnings) == 1
    assert "tokens foi excedido" in warnings[0]
    assert "anexo.pdf" in warnings[0]
    assert "edital.pdf" not in warnings[0]


def test_select_and_prepare_files_for_ai_warning_exceeds_limit(
    mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test case where the base prompt plus the warning message for all files exceeds the token limit."""
    service = AnalysisService(**mock_dependencies)
    service.config.GCP_GEMINI_MAX_INPUT_TOKENS = 50
    files = [("file1.pdf", b"c1"), ("file2.pdf", b"c2")]

    # Mock the token count for a prompt with a warning about all files to be over the limit
    service.ai_provider.count_tokens_for_analysis.return_value = (60, 0, 0)

    selected_files, excluded_files, warnings, tokens = service._select_and_prepare_files_for_ai(files, mock_procurement)

    assert len(selected_files) == 0
    assert len(excluded_files) == 2
    assert "file1.pdf" in excluded_files
    assert "file2.pdf" in excluded_files
    assert tokens == 60


def test_upload_analysis_report(mock_dependencies: dict[str, Any]) -> None:
    """Test that the _upload_analysis_report method calls the GCS provider correctly."""
    service = AnalysisService(**mock_dependencies)
    gcs_base_path = "test/path"
    mock_ai_analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Rationale",
        procurement_summary="Summary",
        analysis_summary="Summary",
        red_flags=[],
        seo_keywords=["keyword1", "keyword2"],
    )

    report_path = service._upload_analysis_report(gcs_base_path, mock_ai_analysis)

    expected_blob_name = f"{gcs_base_path}/analysis_report.json"
    assert report_path == expected_blob_name

    service.gcs_provider.upload_file.assert_called_once()
    call_args = service.gcs_provider.upload_file.call_args[1]
    assert call_args["destination_blob_name"] == expected_blob_name
    assert call_args["content_type"] == "application/json"
    assert b'"risk_score": 5' in call_args["content"]


def test_process_and_save_file_records(mock_dependencies: dict[str, Any]) -> None:
    """Test the happy path for _process_and_save_file_records."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    gcs_base_path = "test/path"
    all_files = [("file1.pdf", b"content1")]
    included_files = [("file1.pdf", b"content1")]
    excluded_files: dict[str, str] = {}

    service._process_and_save_file_records(analysis_id, gcs_base_path, all_files, included_files, excluded_files)

    service.gcs_provider.upload_file.assert_called_once()
    service.file_record_repo.save_file_record.assert_called_once()
    call_args = service.file_record_repo.save_file_record.call_args[0][0]
    assert call_args.analysis_id == analysis_id
    assert call_args.included_in_analysis is True


def test_get_procurement_overall_status(mock_dependencies: dict[str, Any]) -> None:
    """Test that the get_procurement_overall_status method calls the repository."""
    service = AnalysisService(**mock_dependencies)
    control_number = "12345"
    service.analysis_repo.get_procurement_overall_status.return_value = {"status": "OK"}

    status = service.get_procurement_overall_status(control_number)

    service.analysis_repo.get_procurement_overall_status.assert_called_once_with(control_number)
    assert status == {"status": "OK"}


def test_get_procurement_overall_status_not_found(mock_dependencies: dict[str, Any]) -> None:
    """Test that the get_procurement_overall_status method handles not found cases."""
    service = AnalysisService(**mock_dependencies)
    control_number = "12345"
    service.analysis_repo.get_procurement_overall_status.return_value = None

    status = service.get_procurement_overall_status(control_number)

    service.analysis_repo.get_procurement_overall_status.assert_called_once_with(control_number)
    assert status is None


def test_calculate_auto_budget(mock_dependencies: dict[str, Any]) -> None:
    """Test the _calculate_auto_budget method."""
    service = AnalysisService(**mock_dependencies)
    service.budget_ledger_repo.get_total_donations.return_value = 1000
    service.budget_ledger_repo.get_total_expenses_for_period.return_value = 100

    # Mock the date to be the 15th of a 30-day month
    with patch("public_detective.services.analysis.datetime") as mock_datetime:
        mock_datetime.now.return_value.date.return_value = date(2025, 1, 15)
        mock_datetime.side_effect = lambda *args, **kw: datetime(*args, **kw)

        budget = service._calculate_auto_budget("monthly")
        # period_capital = 1000 + 100 = 1100
        # daily_target = 1100 / 31 = 35.48
        # cumulative_target_today = 35.48 * 15 = 532.2
        # budget_for_this_run = 532.2 - 100 = 432.2
        assert budget > 432
        assert budget < 433

        budget = service._calculate_auto_budget("daily")
        assert budget == 1000

        budget = service._calculate_auto_budget("weekly")
        # weekday is Wednesday (2), so day_of_period is 3
        # start_of_period is the 13th
        # daily_target = 1100 / 7 = 157.14
        # cumulative_target_today = 157.14 * 3 = 471.42
        # budget_for_this_run = 471.42 - 100 = 371.42
        assert budget > 371
        assert budget < 372

        with pytest.raises(ValueError):
            service._calculate_auto_budget("invalid")


def test_run_ranked_analysis_happy_path(mock_dependencies: dict[str, Any]) -> None:
    """Test the happy path for run_ranked_analysis."""
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_pending_analyses_ranked.return_value = [
        MagicMock(analysis_id=uuid4(), votes_count=1, total_cost=Decimal("1.00"))
    ]
    service.budget_ledger_repo.get_total_donations.return_value = 1000
    service.budget_ledger_repo.get_total_expenses_for_period.return_value = 100

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        service.run_ranked_analysis(
            use_auto_budget=False,
            budget=Decimal("10.00"),
            budget_period=None,
            zero_vote_budget_percent=10,
        )
        mock_run_specific.assert_called_once()


def test_run_ranked_analysis_auto_budget(mock_dependencies: dict[str, Any]) -> None:
    """Test run_ranked_analysis with auto-budget enabled."""
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_pending_analyses_ranked.return_value = [
        MagicMock(analysis_id=uuid4(), votes_count=1, total_cost=Decimal("1.00"))
    ]

    with patch.object(service, "_calculate_auto_budget", return_value=Decimal("10.00")) as mock_auto_budget:
        with patch.object(service, "run_specific_analysis") as mock_run_specific:
            service.run_ranked_analysis(
                use_auto_budget=True,
                budget_period="daily",
                zero_vote_budget_percent=10,
            )
            mock_auto_budget.assert_called_once_with("daily")
            mock_run_specific.assert_called_once()


def test_run_ranked_analysis_no_budget(mock_dependencies: dict[str, Any]) -> None:
    """Test that run_ranked_analysis raises an error if no budget is provided."""
    service = AnalysisService(**mock_dependencies)
    with pytest.raises(ValueError):
        service.run_ranked_analysis(
            use_auto_budget=False,
            budget=None,
            budget_period=None,
            zero_vote_budget_percent=10,
        )


def test_run_ranked_analysis_max_messages(mock_dependencies: dict[str, Any]) -> None:
    """Test that run_ranked_analysis stops when max_messages is reached."""
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_pending_analyses_ranked.return_value = [
        MagicMock(analysis_id=uuid4(), votes_count=1, total_cost=Decimal("1.00")),
        MagicMock(analysis_id=uuid4(), votes_count=1, total_cost=Decimal("1.00")),
    ]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        service.run_ranked_analysis(
            use_auto_budget=False,
            budget=Decimal("10.00"),
            budget_period=None,
            zero_vote_budget_percent=10,
            max_messages=1,
        )
        assert mock_run_specific.call_count == 1


def test_run_ranked_analysis_budget_exhausted(mock_dependencies: dict[str, Any]) -> None:
    """Test that run_ranked_analysis stops when the budget is exhausted."""
    service = AnalysisService(**mock_dependencies)
    analysis1_id = uuid4()
    analysis2_id = uuid4()
    service.analysis_repo.get_pending_analyses_ranked.return_value = [
        MagicMock(analysis_id=analysis1_id, votes_count=1, total_cost=Decimal("10.00")),
        MagicMock(analysis_id=analysis2_id, votes_count=1, total_cost=Decimal("0.50")),
    ]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        service.run_ranked_analysis(
            use_auto_budget=False,
            budget=Decimal("1.00"),
            budget_period=None,
            zero_vote_budget_percent=10,
        )
        mock_run_specific.assert_called_once_with(analysis2_id)


def test_run_ranked_analysis_zero_vote_budget(mock_dependencies: dict[str, Any]) -> None:
    """Test the zero-vote budget logic."""
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_pending_analyses_ranked.return_value = [
        MagicMock(analysis_id=uuid4(), votes_count=0, total_cost=Decimal("10.00")),
    ]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        service.run_ranked_analysis(
            use_auto_budget=False,
            budget=Decimal("100.00"),
            budget_period=None,
            zero_vote_budget_percent=1,
        )
        mock_run_specific.assert_not_called()


def test_run_ranked_analysis_no_budget_left(mock_dependencies: dict[str, Any]) -> None:
    """Test that run_ranked_analysis stops when there is no budget left."""
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_pending_analyses_ranked.return_value = [
        MagicMock(analysis_id=uuid4(), votes_count=1, total_cost=Decimal("1.00"))
    ]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        service.run_ranked_analysis(
            use_auto_budget=False,
            budget=Decimal("0.00"),
            budget_period=None,
            zero_vote_budget_percent=10,
        )
        mock_run_specific.assert_not_called()


def test_run_ranked_analysis_run_specific_fails(mock_dependencies: dict[str, Any]) -> None:
    """Test that run_ranked_analysis handles exceptions from run_specific_analysis."""
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_pending_analyses_ranked.return_value = [
        MagicMock(analysis_id=uuid4(), votes_count=1, total_cost=Decimal("1.00"))
    ]

    with patch.object(service, "run_specific_analysis", side_effect=Exception("test error")):
        service.run_ranked_analysis(
            use_auto_budget=False,
            budget=Decimal("10.00"),
            budget_period=None,
            zero_vote_budget_percent=10,
        )
        # We don't assert anything here, just that it doesn't crash


def test_run_ranked_analysis_zero_vote_budget_success(mock_dependencies: dict[str, Any]) -> None:
    """Test the zero-vote budget logic with a successful run."""
    service = AnalysisService(**mock_dependencies)
    service.analysis_repo.get_pending_analyses_ranked.return_value = [
        MagicMock(analysis_id=uuid4(), votes_count=0, total_cost=Decimal("1.00")),
    ]

    with patch.object(service, "run_specific_analysis") as mock_run_specific:
        service.run_ranked_analysis(
            use_auto_budget=False,
            budget=Decimal("100.00"),
            budget_period=None,
            zero_vote_budget_percent=10,
        )
        mock_run_specific.assert_called_once()


def test_run_specific_analysis_happy_path(mock_dependencies: dict[str, Any]) -> None:
    """Test the happy path for run_specific_analysis."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    mock_analysis = MagicMock(
        status=ProcurementAnalysisStatus.PENDING_ANALYSIS.value,
        procurement_control_number="123",
        version_number=1,
    )
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis

    service.run_specific_analysis(analysis_id)

    service.analysis_repo.get_analysis_by_id.assert_called_once_with(analysis_id)
    service.pubsub_provider.publish.assert_called_once()


def test_run_specific_analysis_not_found(mock_dependencies: dict[str, Any]) -> None:
    """Test run_specific_analysis when the analysis is not found."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.analysis_repo.get_analysis_by_id.return_value = None

    service.run_specific_analysis(analysis_id)

    service.analysis_repo.get_analysis_by_id.assert_called_once_with(analysis_id)
    service.pubsub_provider.publish.assert_not_called()


def test_run_specific_analysis_wrong_status(mock_dependencies: dict[str, Any]) -> None:
    """Test run_specific_analysis when the analysis is not in PENDING_ANALYSIS state."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    mock_analysis = MagicMock(status=ProcurementAnalysisStatus.ANALYSIS_SUCCESSFUL.value)
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis

    service.run_specific_analysis(analysis_id)

    service.analysis_repo.get_analysis_by_id.assert_called_once_with(analysis_id)
    service.pubsub_provider.publish.assert_not_called()


def test_run_specific_analysis_no_pubsub(mock_dependencies: dict[str, Any]) -> None:
    """Test run_specific_analysis when the pubsub provider is not configured."""
    service = AnalysisService(**mock_dependencies)
    service.pubsub_provider = None
    analysis_id = uuid4()
    mock_analysis = MagicMock(status=ProcurementAnalysisStatus.PENDING_ANALYSIS.value)
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis

    with pytest.raises(AnalysisError) as excinfo:
        service.run_specific_analysis(analysis_id)
    assert "PubSubProvider is not configured" in str(excinfo.value)


def test_process_analysis_from_message_happy_path(
    mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test the happy path for process_analysis_from_message."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    mock_analysis = MagicMock(
        procurement_control_number="123",
        version_number=1,
    )
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    service.procurement_repo.get_procurement_by_id_and_version.return_value = mock_procurement

    with patch.object(service, "analyze_procurement") as mock_analyze_procurement:
        service.process_analysis_from_message(analysis_id)
        mock_analyze_procurement.assert_called_once()


def test_process_analysis_from_message_analysis_not_found(mock_dependencies: dict[str, Any]) -> None:
    """Test process_analysis_from_message when the analysis is not found."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.analysis_repo.get_analysis_by_id.return_value = None

    with patch.object(service, "analyze_procurement") as mock_analyze_procurement:
        service.process_analysis_from_message(analysis_id)
        mock_analyze_procurement.assert_not_called()


def test_process_analysis_from_message_procurement_not_found(mock_dependencies: dict[str, Any]) -> None:
    """Test process_analysis_from_message when the procurement is not found."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    mock_analysis = MagicMock(
        procurement_control_number="123",
        version_number=1,
    )
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    service.procurement_repo.get_procurement_by_id_and_version.return_value = None

    with patch.object(service, "analyze_procurement") as mock_analyze_procurement:
        service.process_analysis_from_message(analysis_id)
        mock_analyze_procurement.assert_not_called()


def test_process_analysis_from_message_analysis_fails(
    mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test process_analysis_from_message when analyze_procurement fails."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    mock_analysis = MagicMock(
        procurement_control_number="123",
        version_number=1,
    )
    service.analysis_repo.get_analysis_by_id.return_value = mock_analysis
    service.procurement_repo.get_procurement_by_id_and_version.return_value = mock_procurement

    with patch.object(service, "analyze_procurement", side_effect=Exception("test error")):
        with pytest.raises(AnalysisError):
            service.process_analysis_from_message(analysis_id)


@patch("public_detective.services.analysis.PricingService")
def test_analyze_procurement_happy_path(
    mock_pricing_service: MagicMock, mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test the happy path for analyze_procurement."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    service.analysis_repo.get_analysis_by_hash.return_value = None
    mock_ai_analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Rationale",
        procurement_summary="Summary",
        analysis_summary="Summary",
        red_flags=[],
        seo_keywords=["keyword1"],
    )
    service.ai_provider.get_structured_analysis.return_value = (mock_ai_analysis, 100, 50, 10)
    mock_pricing_service.return_value.calculate.return_value = (
        Decimal("1"),
        Decimal("2"),
        Decimal("0.5"),
        Decimal("3.5"),
    )

    with patch.object(service, "_get_modality", return_value="text") as mock_get_modality:
        # Mock the token counting for the selection process
        service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)
        service.analyze_procurement(mock_procurement, 1, analysis_id)

        mock_get_modality.assert_called_once()
        service.analysis_repo.save_analysis.assert_called_once()
        call_kwargs = service.analysis_repo.save_analysis.call_args[1]
        assert call_kwargs["total_cost"] == Decimal("3.5")
        assert call_kwargs["thinking_tokens"] == 10
        assert call_kwargs["thinking_cost"] == Decimal("0.5")


@patch("public_detective.services.analysis.PricingService")
def test_analyze_procurement_reuse_existing(
    mock_pricing_service: MagicMock, mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test that analyze_procurement reuses an existing analysis."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    mock_existing_analysis = MagicMock()
    mock_existing_analysis.input_tokens_used = 100
    mock_existing_analysis.output_tokens_used = 50
    mock_existing_analysis.thinking_tokens_used = 10
    mock_existing_analysis.ai_analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Rationale",
        procurement_summary="Summary",
        analysis_summary="Summary",
        red_flags=[],
        seo_keywords=["keyword1"],
    )
    service.analysis_repo.get_analysis_by_hash.return_value = mock_existing_analysis
    mock_pricing_service.return_value.calculate.return_value = (
        Decimal("1"),
        Decimal("2"),
        Decimal("0.5"),
        Decimal("3.5"),
    )

    with patch.object(service, "_get_modality", return_value="text") as mock_get_modality:
        service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)
        service.analyze_procurement(mock_procurement, 1, analysis_id)

        mock_get_modality.assert_called_once()
        service.analysis_repo.save_analysis.assert_called_once()
        # Check that the reused result is passed to save_analysis
        call_args = service.analysis_repo.save_analysis.call_args[1]
        assert call_args["result"].ai_analysis.risk_score == 5
        assert call_args["total_cost"] == Decimal("3.5")


def test_analyze_procurement_no_files(mock_dependencies: dict[str, Any], mock_procurement: Procurement) -> None:
    """Test analyze_procurement when no files are found."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.procurement_repo.process_procurement_documents.return_value = []

    service.analyze_procurement(mock_procurement, 1, analysis_id)

    service.analysis_repo.save_analysis.assert_not_called()


@patch("public_detective.services.analysis.PricingService")
def test_analyze_procurement_reuse_existing_with_gcs_prefix(
    mock_pricing_service: MagicMock, mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test that analyze_procurement reuses an existing analysis with a GCS test prefix."""
    service = AnalysisService(**mock_dependencies)
    service.config.GCP_GCS_TEST_PREFIX = "test-prefix"
    analysis_id = uuid4()
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    mock_existing_analysis = MagicMock()
    mock_existing_analysis.input_tokens_used = 100
    mock_existing_analysis.output_tokens_used = 50
    mock_existing_analysis.thinking_tokens_used = 10
    mock_existing_analysis.ai_analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Rationale",
        procurement_summary="Summary",
        analysis_summary="Summary",
        red_flags=[],
        seo_keywords=["keyword1"],
    )
    service.analysis_repo.get_analysis_by_hash.return_value = mock_existing_analysis
    mock_pricing_service.return_value.calculate.return_value = (
        Decimal("1"),
        Decimal("2"),
        Decimal("0.5"),
        Decimal("3.5"),
    )

    with patch.object(service, "_get_modality", return_value="text") as mock_get_modality:
        service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)
        service.analyze_procurement(mock_procurement, 1, analysis_id)

        mock_get_modality.assert_called_once()
        service.analysis_repo.save_analysis.assert_called_once()
        call_args = service.analysis_repo.save_analysis.call_args[1]
        assert "test-prefix" in call_args["result"].original_documents_gcs_path


@patch("public_detective.services.analysis.PricingService")
def test_analyze_procurement_with_gcs_prefix(
    mock_pricing_service: MagicMock, mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test analyze_procurement with a GCS test prefix."""
    service = AnalysisService(**mock_dependencies)
    service.config.GCP_GCS_TEST_PREFIX = "test-prefix"
    analysis_id = uuid4()
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    service.analysis_repo.get_analysis_by_hash.return_value = None
    mock_ai_analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Rationale",
        procurement_summary="Summary",
        analysis_summary="Summary",
        red_flags=[],
        seo_keywords=["keyword1"],
    )
    service.ai_provider.get_structured_analysis.return_value = (mock_ai_analysis, 100, 50, 10)
    mock_pricing_service.return_value.calculate.return_value = (
        Decimal("1"),
        Decimal("2"),
        Decimal("0.5"),
        Decimal("3.5"),
    )

    with patch.object(service, "_get_modality", return_value="text") as mock_get_modality:
        with patch.object(service, "_upload_analysis_report", return_value="test/path/report.json") as mock_upload:
            service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)
            service.analyze_procurement(mock_procurement, 1, analysis_id)
            mock_upload.assert_called_once()
            assert "test-prefix" in mock_upload.call_args[0][0]
            mock_get_modality.assert_called_once()


def test_get_modality(mock_dependencies: dict[str, Any]) -> None:
    """Test that the _get_modality method returns the correct modality."""
    from public_detective.services.pricing_service import Modality

    service = AnalysisService(**mock_dependencies)
    assert service._get_modality([("file.pdf", b"")]) == Modality.TEXT
    assert service._get_modality([("file.mp4", b"")]) == Modality.VIDEO
    assert service._get_modality([("file.mp3", b"")]) == Modality.AUDIO
    assert service._get_modality([("file.jpg", b"")]) == Modality.IMAGE
    assert service._get_modality([("file.pdf", b""), ("file.mp4", b"")]) == Modality.VIDEO


def test_analyze_procurement_ai_fails(mock_dependencies: dict[str, Any], mock_procurement: Procurement) -> None:
    """Test that analyze_procurement handles AI provider failures."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.procurement_repo.process_procurement_documents.return_value = [("file.pdf", b"content")]
    service.analysis_repo.get_analysis_by_hash.return_value = None
    service.ai_provider.get_structured_analysis.side_effect = Exception("AI error")

    service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)
    with pytest.raises(Exception, match="AI error"):
        service.analyze_procurement(mock_procurement, 1, analysis_id)

    service.analysis_repo.save_analysis.assert_not_called()


def test_analyze_procurement_no_supported_files(
    mock_dependencies: dict[str, Any], mock_procurement: Procurement
) -> None:
    """Test analyze_procurement when no supported files are found."""
    service = AnalysisService(**mock_dependencies)
    analysis_id = uuid4()
    service.procurement_repo.process_procurement_documents.return_value = [("file.txt", b"content")]
    service.ai_provider.count_tokens_for_analysis.return_value = (10, 0, 0)

    service.analyze_procurement(mock_procurement, 1, analysis_id)

    service.analysis_repo.save_analysis.assert_not_called()


