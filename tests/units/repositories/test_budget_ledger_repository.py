from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from repositories.budget_ledger import BudgetLedgerRepository


def test_save_expense() -> None:
    """
    Tests that the save_expense method executes the correct SQL.
    """
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    repo = BudgetLedgerRepository(engine=mock_engine)
    analysis_id = uuid4()
    amount = Decimal("100.50")
    description = "Test expense"

    repo.save_expense(analysis_id, amount, description)

    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    sql = args[0]
    params = args[1]
    assert "INSERT INTO budget_ledgers" in str(sql)
    assert params["analysis_id"] == analysis_id
    assert params["amount"] == amount
    assert params["description"] == description
    mock_conn.commit.assert_called_once()


def test_get_total_donations() -> None:
    """
    Tests that get_total_donations returns the correct sum.
    """
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.scalar_one_or_none.return_value = Decimal("1234.56")
    repo = BudgetLedgerRepository(engine=mock_engine)

    total = repo.get_total_donations()

    assert total == Decimal("1234.56")


def test_get_total_donations_no_donations() -> None:
    """
    Tests that get_total_donations returns 0 when there are no donations.
    """
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.scalar_one_or_none.return_value = None
    repo = BudgetLedgerRepository(engine=mock_engine)

    total = repo.get_total_donations()

    assert total == Decimal("0")


def test_get_total_expenses_for_period() -> None:
    """
    Tests that get_total_expenses_for_period returns the correct sum.
    """
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.scalar_one_or_none.return_value = Decimal("567.89")
    repo = BudgetLedgerRepository(engine=mock_engine)
    start_date = date(2025, 1, 1)

    total = repo.get_total_expenses_for_period(start_date)

    assert total == Decimal("567.89")
    mock_conn.execute.assert_called_once()
    args, _ = mock_conn.execute.call_args
    params = args[1]
    assert params["start_date"] == start_date


def test_get_total_expenses_for_period_no_expenses() -> None:
    """
    Tests that get_total_expenses_for_period returns 0 when there are no expenses.
    """
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__.return_value = mock_conn
    mock_conn.execute.return_value.scalar_one_or_none.return_value = None
    repo = BudgetLedgerRepository(engine=mock_engine)
    start_date = date(2025, 1, 1)

    total = repo.get_total_expenses_for_period(start_date)

    assert total == Decimal("0")
