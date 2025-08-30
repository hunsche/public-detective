"""
Unit tests for the analysis models.
"""

import json

import pytest
from models.analysis import Analysis, RedFlag, RedFlagCategory


def test_red_flag_creation():
    """Tests the creation of a RedFlag object."""
    red_flag = RedFlag(
        category=RedFlagCategory.DIRECTING,
        description="Test description",
        evidence_quote="Test quote",
        auditor_reasoning="Test reasoning",
    )
    assert red_flag.category == RedFlagCategory.DIRECTING
    assert red_flag.description == "Test description"


def test_analysis_creation():
    """Tests the creation of an Analysis object."""
    analysis = Analysis(
        risk_score=5,
        risk_score_rationale="Test rationale",
        red_flags=[],
    )
    assert analysis.risk_score == 5
    assert analysis.risk_score_rationale == "Test rationale"


def test_parse_red_flags_validator():
    """Tests the parse_red_flags validator."""
    # Test with a list of dicts
    red_flags_dicts = [
        {
            "category": "DIRECIONAMENTO",
            "description": "Test",
            "evidence_quote": "Test",
            "auditor_reasoning": "Test",
        }
    ]
    analysis = Analysis(risk_score=1, risk_score_rationale="test", findings=red_flags_dicts)
    assert isinstance(analysis.red_flags[0], RedFlag)

    # Test with a list of JSON strings
    red_flags_json = [json.dumps(flag) for flag in red_flags_dicts]
    analysis = Analysis(risk_score=1, risk_score_rationale="test", findings=red_flags_json)
    assert isinstance(analysis.red_flags[0], RedFlag)

    # Test with invalid JSON string
    red_flags_invalid_json = ["invalid json"]
    analysis = Analysis(risk_score=1, risk_score_rationale="test", findings=red_flags_invalid_json)
    assert analysis.red_flags == []

    # Test with a mix of valid and invalid
    red_flags_mixed = [red_flags_dicts[0], "invalid json"]
    analysis = Analysis(risk_score=1, risk_score_rationale="test", findings=red_flags_mixed)
    assert len(analysis.red_flags) == 1
    assert isinstance(analysis.red_flags[0], RedFlag)

    # Test with non-list input
    with pytest.raises(ValueError):
        Analysis(risk_score=1, risk_score_rationale="test", findings="not a list")
