import json
from decimal import Decimal
from unittest.mock import MagicMock, patch
from uuid import UUID, uuid4

import pytest
from public_detective.models.analyses import AnalysisResult, RedFlag, RedFlagCategory
from public_detective.models.procurement_analysis_status import ProcurementAnalysisStatus
from public_detective.repositories.analyses import AnalysisRepository


@pytest.fixture
def mock_engine() -> MagicMock:
    """Fixture for a mocked database engine.

    Returns:
        A MagicMock object.
    """
    return MagicMock()


@pytest.fixture
def analysis_repository(mock_engine: MagicMock) -> AnalysisRepository:
    """
    Fixture to create an AnalysisRepository with a mocked database engine.

    Args:
        mock_engine: The mocked database engine.

    Returns:
        An instance of AnalysisRepository.
    """
    return AnalysisRepository(engine=mock_engine)


def test_parse_row_to_model_with_seo_keywords(analysis_repository: AnalysisRepository) -> None:
    """
    Should correctly parse a row that includes seo_keywords.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    columns = [
        "procurement_control_number",
        "risk_score",
        "risk_score_rationale",
        "red_flags",
        "seo_keywords",
        "analysis_prompt",
    ]
    red_flags_list: list = []
    seo_keywords_list = ["keyword1", "keyword2"]
    row_tuple = (
        "12345",
        8,
        "High risk",
        json.dumps(red_flags_list),
        seo_keywords_list,
        "Test prompt",
    )

    # Act
    result = analysis_repository._parse_row_to_model(row_tuple, columns)

    # Assert
    assert result is not None
    assert result.ai_analysis.seo_keywords == ["keyword1", "keyword2"]


def test_parse_row_to_model_with_json_string(analysis_repository: AnalysisRepository) -> None:
    """
    Should correctly parse a row where 'red_flags' is a JSON string.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    columns = [
        "procurement_control_number",
        "risk_score",
        "risk_score_rationale",
        "red_flags",
        "analysis_prompt",
    ]
    red_flags_list = [
        {
            "category": "SOBREPRECO",
            "severity": "MODERADA",
            "description": "Test description",
            "evidence_quote": "Test quote",
            "auditor_reasoning": "Test reasoning",
        }
    ]
    row_tuple = (
        "12345",
        8,
        "High risk",
        json.dumps(red_flags_list),  # red_flags as a JSON string
        "Test prompt",
    )

    # Act
    result = analysis_repository._parse_row_to_model(row_tuple, columns)

    # Assert
    assert result is not None
    assert isinstance(result, AnalysisResult)
    assert result.procurement_control_number == "12345"
    assert result.ai_analysis.risk_score == 8
    assert len(result.ai_analysis.red_flags) == 1
    assert isinstance(result.ai_analysis.red_flags[0], RedFlag)
    assert result.ai_analysis.red_flags[0].category == RedFlagCategory.OVERPRICE


def test_parse_row_to_model_with_dict(analysis_repository: AnalysisRepository) -> None:
    """
    Should correctly parse a row where 'red_flags' is already a dict/list.
    This simulates the behavior of the DB driver already deserializing the JSON.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    columns = [
        "procurement_control_number",
        "risk_score",
        "risk_score_rationale",
        "red_flags",
        "analysis_prompt",
    ]
    red_flags_list = [
        {
            "category": "DIRECIONAMENTO",
            "severity": "GRAVE",
            "description": "Test description 2",
            "evidence_quote": "Test quote 2",
            "auditor_reasoning": "Test reasoning 2",
        }
    ]
    row_tuple = (
        "67890",
        5,
        "Medium risk",
        red_flags_list,  # red_flags as a Python list
        "Test prompt",
    )

    # Act
    result = analysis_repository._parse_row_to_model(row_tuple, columns)

    # Assert
    assert result is not None
    assert isinstance(result, AnalysisResult)
    assert result.procurement_control_number == "67890"
    assert result.ai_analysis.risk_score == 5
    assert len(result.ai_analysis.red_flags) == 1
    assert isinstance(result.ai_analysis.red_flags[0], RedFlag)
    assert result.ai_analysis.red_flags[0].category == RedFlagCategory.DIRECTING


@patch("public_detective.repositories.analyses.LoggingProvider")
def test_parse_row_to_model_with_invalid_data(
    mock_logging_provider: MagicMock, analysis_repository: AnalysisRepository
) -> None:
    """
    Should return None and log an error if parsing fails.

    Args:
        mock_logging_provider: Mock for the LoggingProvider.
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger

    analysis_repository.logger = mock_logger

    columns = ["risk_score"]
    row_tuple = ("not_an_int",)  # Invalid data type for risk_score

    # Act
    result = analysis_repository._parse_row_to_model(row_tuple, columns)

    # Assert
    assert result is None
    mock_logger.error.assert_called_once()
    assert "Failed to parse analysis result from DB due to validation error" in mock_logger.error.call_args[0][0]


def test_save_analysis_updates_record(analysis_repository: AnalysisRepository) -> None:
    """
    Should execute an UPDATE statement with the correct parameters.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    mock_conn = MagicMock()
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    analysis_id = uuid4()
    analysis_result = AnalysisResult(
        procurement_control_number="PNCP-123",
        version_number=1,
        document_hash="test-hash",
        analysis_prompt="Test prompt",
        ai_analysis={
            "risk_score": 8,
            "risk_score_rationale": "High risk",
            "procurement_summary": "Test procurement summary",
            "analysis_summary": "Test analysis summary",
            "red_flags": [],
            "seo_keywords": ["keyword1", "keyword2"],
        },
        warnings=["Warning 1"],
        original_documents_gcs_path="gcs://bucket/orig",
        processed_documents_gcs_path="gcs://bucket/proc",
    )

    # Act
    analysis_repository.save_analysis(
        analysis_id=analysis_id,
        result=analysis_result,
        input_tokens=100,
        output_tokens=50,
        thinking_tokens=10,
        input_cost=Decimal("0.1"),
        output_cost=Decimal("0.2"),
        thinking_cost=Decimal("0.05"),
        total_cost=Decimal("0.35"),
        search_cost=Decimal("0.0"),
        search_queries_used=0,
    )

    # Assert
    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    params = args[1]
    assert params["analysis_id"] == analysis_id
    assert params["risk_score"] == 8
    assert params["seo_keywords"] == ["keyword1", "keyword2"]
    assert "UPDATE procurement_analyses" in str(args[0])
    assert "seo_keywords = :seo_keywords" in str(args[0])
    assert params["thinking_tokens_used"] == 10
    assert params["cost_thinking_tokens"] == Decimal("0.05")
    assert params["total_cost"] == Decimal("0.35")
    assert params["cost_search_queries"] == Decimal("0.0")
    assert params["search_queries_used"] == 0


def test_parse_row_to_model_empty_row(analysis_repository: AnalysisRepository) -> None:
    """Should return None for an empty row.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    assert analysis_repository._parse_row_to_model(None, []) is None


def test_parse_row_to_model_invalid_json(analysis_repository: AnalysisRepository) -> None:
    """Should raise JSONDecodeError if red_flags contains invalid JSON.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    columns = [
        "procurement_control_number",
        "risk_score",
        "risk_score_rationale",
        "red_flags",
    ]
    row_tuple = (
        "12345",
        8,
        "High risk",
        "this is not valid json",
    )
    with pytest.raises(json.JSONDecodeError):
        analysis_repository._parse_row_to_model(row_tuple, columns)


def test_get_analysis_by_hash_not_found(analysis_repository: AnalysisRepository) -> None:
    """Should return None when no analysis is found for a given hash.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_result_proxy.fetchone.return_value = None
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    result = analysis_repository.get_analysis_by_hash("nonexistent_hash")

    assert result is None


def test_create_pre_analysis_record_returns_id(analysis_repository: AnalysisRepository) -> None:
    """
    Should return the ID of the newly inserted pre-analysis record.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_result_proxy.scalar_one.return_value = uuid4()
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    # Act
    returned_id = analysis_repository.create_pre_analysis_record(
        procurement_control_number="PNCP-456",
        version_number=1,
        document_hash="pre-analysis-hash",
    )

    # Assert
    assert isinstance(returned_id, UUID)
    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    params = args[1]
    assert params["procurement_control_number"] == "PNCP-456"
    assert params["version_number"] == 1
    assert params["document_hash"] == "pre-analysis-hash"
    assert params["status"] == ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value
    assert "INSERT INTO procurement_analyses" in str(args[0])
    assert "status, document_hash" in str(args[0])
    assert "PENDING_TOKEN_CALCULATION" in str(args[1]["status"])


def test_get_analysis_by_id_not_found(analysis_repository: AnalysisRepository) -> None:
    """Should return None when no analysis is found for a given ID.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_result_proxy.fetchone.return_value = None
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    result = analysis_repository.get_analysis_by_id(uuid4())

    assert result is None


def test_parse_row_to_model_with_none_red_flags(analysis_repository: AnalysisRepository) -> None:
    """
    Should correctly parse a row where 'red_flags' is None.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    columns = [
        "procurement_control_number",
        "risk_score",
        "risk_score_rationale",
        "red_flags",
        "analysis_prompt",
    ]
    row_tuple = (
        "12345",
        8,
        "High risk",
        None,
        "Test prompt",
    )

    # Act
    result = analysis_repository._parse_row_to_model(row_tuple, columns)

    # Assert
    assert result is not None
    assert result.ai_analysis.red_flags == []


def test_get_analysis_by_hash_found(analysis_repository: AnalysisRepository) -> None:
    """Should return an AnalysisResult when an analysis is found for a given hash.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_row = MagicMock()
    mock_row._fields = ["procurement_control_number"]
    mock_result_proxy.fetchone.return_value = mock_row
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    with patch.object(
        analysis_repository, "_parse_row_to_model", return_value=MagicMock(spec=AnalysisResult)
    ) as mock_parse:
        result = analysis_repository.get_analysis_by_hash("existent_hash")

    assert result is not None
    mock_parse.assert_called_once()


def test_get_procurement_overall_status_found(analysis_repository: AnalysisRepository) -> None:
    """
    Should return a dictionary with status info when a record is found.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_row = MagicMock()
    mock_row._mapping = {
        "procurement_id": "PNCP-123",
        "latest_version": 2,
        "overall_status": "ANALYZED_CURRENT",
    }
    mock_result_proxy.fetchone.return_value = mock_row
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    # Act
    result = analysis_repository.get_procurement_overall_status("PNCP-123")

    # Assert
    assert result is not None
    assert result["procurement_id"] == "PNCP-123"
    assert result["overall_status"] == "ANALYZED_CURRENT"
    mock_conn.execute.assert_called_once()


def test_get_procurement_overall_status_not_found(analysis_repository: AnalysisRepository) -> None:
    """
    Should return None when no record is found for the given control number.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_result_proxy.fetchone.return_value = None  # Simulate no record found
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    # Act
    result = analysis_repository.get_procurement_overall_status("PNCP-999")

    # Assert
    assert result is None
    mock_conn.execute.assert_called_once()


def test_get_analyses_to_retry_not_found(analysis_repository: AnalysisRepository) -> None:
    """
    Should return an empty list when no analyses are found to retry.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_result_proxy.fetchall.return_value = []
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    # Act
    result = analysis_repository.get_analyses_to_retry(3, 1)

    # Assert
    assert result == []
    mock_conn.execute.assert_called_once()


@patch("public_detective.repositories.analyses.LoggingProvider")
def test_update_analysis_status(mock_logging_provider: MagicMock, analysis_repository: AnalysisRepository) -> None:
    """Should execute an UPDATE statement with the correct parameters."""
    mock_logger = MagicMock()
    mock_logging_provider.return_value.get_logger.return_value = mock_logger
    analysis_repository.logger = mock_logger

    mock_conn = MagicMock()
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn
    analysis_id = uuid4()
    status = ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS

    analysis_repository.update_analysis_status(analysis_id, status)

    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    params = args[1]
    assert params["analysis_id"] == analysis_id
    assert params["status"] == status.value
    assert "UPDATE procurement_analyses" in str(args[0])
    assert mock_logger.info.call_count == 2


def test_get_analyses_to_retry(analysis_repository: AnalysisRepository) -> None:
    """Should return a list of analyses to retry."""
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_row = MagicMock()
    mock_row._fields = ["procurement_control_number"]
    mock_result_proxy.fetchall.return_value = [mock_row]
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    with patch.object(
        analysis_repository, "_parse_row_to_model", return_value=MagicMock(spec=AnalysisResult)
    ) as mock_parse:
        result = analysis_repository.get_analyses_to_retry(3, 1)

    assert result is not None
    assert len(result) == 1
    mock_parse.assert_called_once()


def test_save_retry_analysis_returns_id(analysis_repository: AnalysisRepository) -> None:
    """
    Should return the ID of the newly inserted retry analysis record.
    """
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_result_proxy.scalar_one.side_effect = [
        uuid4(),
        None,
        None,
    ]  # First call returns UUID, subsequent return None for updates
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    returned_id = analysis_repository.save_retry_analysis(
        procurement_control_number="PNCP-789",
        version_number=1,
        document_hash="retry-hash",
        input_tokens_used=200,
        output_tokens_used=100,
        thinking_tokens_used=50,
        input_cost=Decimal("0.2"),
        output_cost=Decimal("0.3"),
        thinking_cost=Decimal("0.1"),
        total_cost=Decimal("0.6"),
        search_cost=Decimal("0.0"),
        search_queries_used=0,
        retry_count=1,
        analysis_prompt="Test prompt",
    )

    assert isinstance(returned_id, UUID)
    assert mock_conn.execute.call_count == 3

    # Assert call for create_pre_analysis_record
    create_call_args, _ = mock_conn.execute.call_args_list[0]
    create_params = create_call_args[1]
    assert create_params["procurement_control_number"] == "PNCP-789"
    assert create_params["version_number"] == 1
    assert create_params["document_hash"] == "retry-hash"
    assert create_params["retry_count"] == 1
    assert create_params["status"] == ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value
    assert "INSERT INTO procurement_analyses" in str(create_call_args[0])

    # Assert call for update_pre_analysis_with_tokens
    update_tokens_call_args, _ = mock_conn.execute.call_args_list[1]
    update_tokens_params = update_tokens_call_args[1]
    assert update_tokens_params["analysis_id"] == returned_id
    assert update_tokens_params["input_tokens_used"] == 200
    assert update_tokens_params["total_cost"] == Decimal("0.6")
    assert "UPDATE procurement_analyses" in str(update_tokens_call_args[0])

    # Assert call for update_analysis_status
    update_status_call_args, _ = mock_conn.execute.call_args_list[2]
    update_status_params = update_status_call_args[1]
    assert update_status_params["analysis_id"] == returned_id
    assert update_status_params["status"] == ProcurementAnalysisStatus.PENDING_ANALYSIS.value
    assert "UPDATE procurement_analyses" in str(update_status_call_args[0])


def test_get_analyses_to_retry_includes_pending_token_calculation(
    analysis_repository: AnalysisRepository,
) -> None:
    """
    Should include analyses stuck in PENDING_TOKEN_CALCULATION in the retry list.

    Args:
        analysis_repository: The AnalysisRepository instance.
    """
    # Arrange
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_row = MagicMock()
    mock_row._fields = ["procurement_control_number", "status"]
    mock_row.__iter__.return_value = ["PNCP-STUCK", ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value]
    mock_result_proxy.fetchall.return_value = [mock_row]
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    mock_analysis_result = MagicMock(spec=AnalysisResult)
    mock_analysis_result.status = ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value

    with patch.object(analysis_repository, "_parse_row_to_model", return_value=mock_analysis_result) as mock_parse:
        # Act
        result = analysis_repository.get_analyses_to_retry(max_retries=3, timeout_hours=1)

    # Assert
    assert result is not None
    assert len(result) == 1
    assert result[0].status == ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value
    mock_parse.assert_called_once()

    # Check the params passed to the query
    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    params = args[1]
    assert params["failed_status"] == ProcurementAnalysisStatus.ANALYSIS_FAILED.value
    assert params["in_progress_status"] == ProcurementAnalysisStatus.ANALYSIS_IN_PROGRESS.value
    assert params["pending_token_status"] == ProcurementAnalysisStatus.PENDING_TOKEN_CALCULATION.value
    assert "status = :pending_token_status" in str(args[0])


def test_get_pending_analyses_ranked(analysis_repository: AnalysisRepository) -> None:
    """Should return a list of pending analyses."""
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_row = MagicMock()
    mock_row._fields = ["procurement_control_number"]
    mock_result_proxy.fetchall.return_value = [mock_row]
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    with patch.object(
        analysis_repository, "_parse_row_to_model", return_value=MagicMock(spec=AnalysisResult)
    ) as mock_parse:
        result = analysis_repository.get_pending_analyses_ranked()

    assert result is not None
    assert len(result) == 1
    mock_parse.assert_called_once()


def test_get_pending_analyses_ranked_not_found(analysis_repository: AnalysisRepository) -> None:
    """Should return an empty list when no pending analyses are found."""
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_result_proxy.fetchall.return_value = []
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    result = analysis_repository.get_pending_analyses_ranked()

    assert result == []
