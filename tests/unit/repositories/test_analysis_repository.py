import json

import pytest
from models.analysis import AnalysisResult, RedFlag, RedFlagCategory
from repositories.analysis import AnalysisRepository


@pytest.fixture
def analysis_repository(mocker):
    """
    Fixture to create an AnalysisRepository with a mocked database engine.
    """
    mocker.patch("providers.database.DatabaseManager.get_engine")
    return AnalysisRepository()


def test_parse_row_to_model_with_json_string(analysis_repository):
    """
    Should correctly parse a row where 'red_flags' is a JSON string.
    """
    # Arrange
    columns = [
        "procurement_control_number",
        "risk_score",
        "risk_score_rationale",
        "summary",
        "red_flags",
    ]
    red_flags_list = [
        {
            "category": "OVERPRICE",
            "description": "Test description",
            "evidence_quote": "Test quote",
            "auditor_reasoning": "Test reasoning",
        }
    ]
    row_tuple = (
        "12345",
        8,
        "High risk",
        "Summary",
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
        "summary",
        "red_flags",
    ]
    red_flags_list = [
        {
            "category": "DIRECTING",
            "description": "Test description 2",
            "evidence_quote": "Test quote 2",
            "auditor_reasoning": "Test reasoning 2",
        }
    ]
    row_tuple = (
        "67890",
        5,
        "Medium risk",
        "Another Summary",
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
