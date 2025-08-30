import json
from unittest.mock import MagicMock, patch

import pytest
from models.analysis import AnalysisResult, RedFlag, RedFlagCategory
from repositories.analysis import AnalysisRepository


@pytest.fixture
def mock_engine():
    """Fixture for a mocked database engine."""
    return MagicMock()


@pytest.fixture
def analysis_repository(mock_engine):
    """
    Fixture to create an AnalysisRepository with a mocked database engine.
    """
    return AnalysisRepository(engine=mock_engine)


def test_parse_row_to_model_with_json_string(analysis_repository):
    """
    Should correctly parse a row where 'red_flags' is a JSON string.
    """
    # Arrange
    columns = [
        "procurement_control_number",
        "risk_score",
        "risk_score_rationale",
        "red_flags",
    ]
    red_flags_list = [
        {
            "category": "SOBREPRECO",
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


def test_parse_row_to_model_with_dict(analysis_repository):
    """
    Should correctly parse a row where 'red_flags' is already a dict/list.
    This simulates the behavior of the DB driver already deserializing the JSON.
    """
    # Arrange
    columns = [
        "procurement_control_number",
        "risk_score",
        "risk_score_rationale",
        "red_flags",
    ]
    red_flags_list = [
        {
            "category": "DIRECIONAMENTO",
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


def test_parse_row_to_model_with_invalid_data(analysis_repository, caplog):
    """
    Should return None and log an error if parsing fails.
    """
    # Arrange
    columns = ["risk_score"]
    row_tuple = ("not_an_int",)  # Invalid data type for risk_score

    # Act
    result = analysis_repository._parse_row_to_model(row_tuple, columns)

    # Assert
    assert result is None
    assert "Failed to parse analysis result from DB" in caplog.text


def test_save_analysis_updates_record(analysis_repository):
    """
    Should execute an UPDATE statement with the correct parameters.
    """
    # Arrange
    mock_conn = MagicMock()
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    analysis_id = 123
    analysis_result = AnalysisResult(
        procurement_control_number="PNCP-123",
        version_number=1,
        document_hash="test-hash",
        ai_analysis={
            "risk_score": 8,
            "risk_score_rationale": "High risk",
            "red_flags": [],
        },
        warnings=["Warning 1"],
        original_documents_gcs_path="gcs://bucket/orig",
        processed_documents_gcs_path="gcs://bucket/proc",
    )

    # Act
    analysis_repository.save_analysis(analysis_id, analysis_result)

    # Assert
    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    params = args[1]
    assert params["analysis_id"] == analysis_id
    assert params["risk_score"] == 8
    assert "UPDATE procurement_analysis" in str(args[0])


def test_parse_row_to_model_empty_row(analysis_repository):
    """Should return None for an empty row."""
    assert analysis_repository._parse_row_to_model(None, []) is None


def test_parse_row_to_model_invalid_json(analysis_repository):
    """Should raise JSONDecodeError if red_flags contains invalid JSON."""
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


def test_get_analysis_by_hash_not_found(analysis_repository):
    """Should return None when no analysis is found for a given hash."""
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_result_proxy.fetchone.return_value = None
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    result = analysis_repository.get_analysis_by_hash("nonexistent_hash")

    assert result is None


def test_save_pre_analysis_returns_id(analysis_repository):
    """
    Should return the ID of the newly inserted pre-analysis record.
    """
    # Arrange
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_result_proxy.scalar_one.return_value = 456
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    # Act
    returned_id = analysis_repository.save_pre_analysis(
        "PNCP-456",
        1,
        1.23,
        "pre-analysis-hash",
    )

    # Assert
    assert returned_id == 456
    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    params = args[1]
    assert params["procurement_control_number"] == "PNCP-456"
    assert params["version_number"] == 1
    assert params["estimated_cost"] == 1.23
    assert params["document_hash"] == "pre-analysis-hash"


def test_get_analysis_by_id_not_found(analysis_repository):
    """Should return None when no analysis is found for a given ID."""
    mock_conn = MagicMock()
    mock_result_proxy = MagicMock()
    mock_result_proxy.fetchone.return_value = None
    mock_conn.execute.return_value = mock_result_proxy
    analysis_repository.engine.connect.return_value.__enter__.return_value = mock_conn

    result = analysis_repository.get_analysis_by_id(999)

    assert result is None


def test_parse_row_to_model_with_none_red_flags(analysis_repository):
    """
    Should correctly parse a row where 'red_flags' is None.
    """
    # Arrange
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
        None,
    )

    # Act
    result = analysis_repository._parse_row_to_model(row_tuple, columns)

    # Assert
    assert result is not None
    assert result.ai_analysis.red_flags == []


def test_get_analysis_by_hash_found(analysis_repository):
    """Should return an AnalysisResult when an analysis is found for a given hash."""
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