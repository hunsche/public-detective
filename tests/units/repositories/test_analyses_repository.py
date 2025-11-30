"""Unit tests for AnalysisRepository."""

from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from public_detective.repositories.analyses import AnalysisRepository
from sqlalchemy import Engine


@pytest.fixture
def mock_engine() -> MagicMock:
    """Mock the SQLAlchemy engine."""
    return MagicMock(spec=Engine)


@pytest.fixture
def mock_connection(mock_engine: MagicMock) -> MagicMock:
    """Mock the database connection."""
    connection = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = connection
    return connection


@pytest.fixture
def repository(mock_engine: MagicMock) -> AnalysisRepository:
    """Create an AnalysisRepository instance."""
    return AnalysisRepository(mock_engine)


def test_get_latest_analysis_with_files(repository: AnalysisRepository, mock_connection: MagicMock) -> None:
    """Test retrieving the latest analysis with files."""
    analysis_id = uuid4()
    mock_connection.execute.return_value.scalar_one_or_none.return_value = analysis_id

    result = repository.get_latest_analysis_with_files("123456", 1)

    assert result == analysis_id
    mock_connection.execute.assert_called_once()


def test_get_analysis_by_id(repository: AnalysisRepository, mock_connection: MagicMock) -> None:
    """Test retrieving an analysis by ID."""
    analysis_id = uuid4()
    mock_row = MagicMock()
    mock_row._fields = (
        "analysis_id",
        "procurement_control_number",
        "version_number",
        "status",
        "risk_score",
        "risk_score_rationale",
        "procurement_summary",
        "analysis_summary",
        "red_flags",
        "seo_keywords",
        "document_hash",
        "original_documents_gcs_path",
        "processed_documents_gcs_path",
        "input_tokens_used",
        "output_tokens_used",
        "thinking_tokens_used",
        "created_at",
        "updated_at",
        "retry_count",
        "votes_count",
        "cost_input_tokens",
        "cost_output_tokens",
        "cost_thinking_tokens",
        "cost_search_queries",
        "search_queries_used",
        "total_cost",
        "analysis_prompt",
        "thoughts",
    )
    mock_row.__iter__.return_value = iter(
        [
            analysis_id,
            "123456",
            1,
            "ANALYSIS_SUCCESSFUL",
            80,
            "Rationale",
            "Summary",
            "Analysis Summary",
            "[]",
            [],
            "hash",
            "path/to/original",
            "path/to/processed",
            100,
            100,
            100,
            None,
            None,
            0,
            0,
            Decimal("0.1"),
            Decimal("0.1"),
            Decimal("0.1"),
            Decimal("0.1"),
            1,
            Decimal("0.4"),
            "Prompt",
            "Thoughts",
        ]
    )
    mock_connection.execute.return_value.fetchone.return_value = mock_row

    result = repository.get_analysis_by_id(analysis_id)

    assert result is not None
    assert result.analysis_id == analysis_id
    assert result.procurement_control_number == "123456"


def test_get_analysis_by_id_not_found(repository: AnalysisRepository, mock_connection: MagicMock) -> None:
    """Test retrieving an analysis by ID when not found."""
    mock_connection.execute.return_value.fetchone.return_value = None

    result = repository.get_analysis_by_id(uuid4())

    assert result is None


def test_get_home_stats(repository: AnalysisRepository, mock_connection: MagicMock) -> None:
    """Test retrieving home stats."""
    # Mock return values for the three queries
    mock_connection.execute.side_effect = [
        MagicMock(scalar=lambda: 10),  # total_analyses
        MagicMock(scalar=lambda: 5),  # high_risk_count
        MagicMock(scalar=lambda: 1000.0),  # total_savings
    ]

    stats = repository.get_home_stats()

    assert stats["total_analyses"] == 10
    assert stats["high_risk_count"] == 5
    assert stats["total_savings"] == 1000.0


def test_get_recent_analyses_summary(repository: AnalysisRepository, mock_connection: MagicMock) -> None:
    """Test retrieving recent analyses summary."""
    # Mock total count
    mock_connection.execute.side_effect = [
        MagicMock(scalar=lambda: 1),  # total_count
        MagicMock(fetchall=lambda: []),  # result (empty for now to simplify)
    ]

    results, count = repository.get_recent_analyses_summary(page=1, limit=10)

    assert count == 1
    assert results == []


def test_search_analyses_summary(repository: AnalysisRepository, mock_connection: MagicMock) -> None:
    """Test searching analyses summary."""
    # Mock total count
    mock_connection.execute.side_effect = [
        MagicMock(scalar=lambda: 1),  # total_count
        MagicMock(fetchall=lambda: []),  # result
    ]

    results, count = repository.search_analyses_summary("query", page=1, limit=10)

    assert count == 1
    assert results == []


def test_get_analysis_details(repository: AnalysisRepository, mock_connection: MagicMock) -> None:
    """Test retrieving analysis details."""
    analysis_id = uuid4()
    mock_result = MagicMock()
    mock_result._mapping = {"analysis_id": analysis_id, "total_estimated_value": 1000.0}
    mock_connection.execute.return_value.fetchone.return_value = mock_result

    result = repository.get_analysis_details(analysis_id)

    assert result is not None
    assert result["analysis_id"] == analysis_id
    assert result["total_estimated_value"] == 1000.0


def test_get_analysis_details_not_found(repository: AnalysisRepository, mock_connection: MagicMock) -> None:
    """Test retrieving analysis details when not found."""
    mock_connection.execute.return_value.fetchone.return_value = None

    result = repository.get_analysis_details(uuid4())

    assert result is None
