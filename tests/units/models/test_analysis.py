"""
Unit tests for the analysis models.
"""

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


def test_red_flag_parsing():
    """Tests that red_flags are correctly parsed from dicts."""
    # Test with a list of dicts
    red_flags_dicts = [
        {
            "category": "DIRECIONAMENTO",
            "description": "Test",
            "evidence_quote": "Test",
            "auditor_reasoning": "Test",
        }
    ]
    analysis = Analysis(risk_score=1, risk_score_rationale="test", red_flags=red_flags_dicts)
    assert isinstance(analysis.red_flags[0], RedFlag)
