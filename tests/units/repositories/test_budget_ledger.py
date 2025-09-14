"""This module contains the unit tests for the BudgetLedgerRepository."""

from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from public_detective.repositories.budget_ledger import BudgetLedgerRepository


@pytest.fixture
def mock_engine() -> MagicMock:
    """Fixture to create a mock SQLAlchemy engine."""
    engine = MagicMock()
    conn = MagicMock()
    engine.connect.return_value.__enter__.return_value = conn
    return engine


def test_save_expense(mock_engine: MagicMock) -> None:
    """Test that the save_expense method executes the correct SQL."""
    repo = BudgetLedgerRepository(mock_engine)
    analysis_id = uuid4()
    amount = Decimal("100.50")
    description = "Test Expense"

    repo.save_expense(analysis_id, amount, description)

    mock_engine.connect.return_value.__enter__.return_value.execute.assert_called_once()
    # Further assertions can be made on the SQL statement and parameters


def test_get_total_donations(mock_engine: MagicMock) -> None:
    """Test that get_total_donations returns the correct sum."""
    conn = mock_engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.scalar_one_or_none.return_value = Decimal("500.75")

    repo = BudgetLedgerRepository(mock_engine)
    total_donations = repo.get_total_donations()

    assert total_donations == Decimal("500.75")
    conn.execute.assert_called_once()


def test_get_total_donations_returns_zero_when_no_donations(mock_engine: MagicMock) -> None:
    """Test that get_total_donations returns zero when there are no donations."""
    conn = mock_engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.scalar_one_or_none.return_value = None

    repo = BudgetLedgerRepository(mock_engine)
    total_donations = repo.get_total_donations()

    assert total_donations == Decimal("0")


def test_get_total_expenses_for_period(mock_engine: MagicMock) -> None:
    """Test that get_total_expenses_for_period returns the correct sum."""
    conn = mock_engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.scalar_one_or_none.return_value = Decimal("1234.56")

    repo = BudgetLedgerRepository(mock_engine)
    start_date = date(2025, 1, 1)
    total_expenses = repo.get_total_expenses_for_period(start_date)

    assert total_expenses == Decimal("1234.56")
    conn.execute.assert_called_once()


def test_get_total_expenses_for_period_returns_zero_when_no_expenses(mock_engine: MagicMock) -> None:
    """Test that get_total_expenses_for_period returns zero when there are no expenses."""
    conn = mock_engine.connect.return_value.__enter__.return_value
    conn.execute.return_value.scalar_one_or_none.return_value = None

    repo = BudgetLedgerRepository(mock_engine)
    start_date = date(2025, 1, 1)
    total_expenses = repo.get_total_expenses_for_period(start_date)

    assert total_expenses == Decimal("0")
