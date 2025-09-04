from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from source.repositories.budget_ledger import BudgetLedgerRepository


def test_save_expense():
    """
    Tests that the save_expense method correctly executes an INSERT statement.
    """
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value = mock_conn
    repo = BudgetLedgerRepository(engine=mock_engine)

    analysis_id = uuid4()
    cost = Decimal("123.45")
    description = "Test expense"

    repo.save_expense(analysis_id, cost, description)

    mock_conn.__enter__().execute.assert_called_once()
    call_args, _ = mock_conn.__enter__().execute.call_args
    sql_statement = call_args[0].text
    params = call_args[1]

    assert "INSERT INTO budget_ledgers" in sql_statement
    assert params["related_analysis_id"] == analysis_id
    assert params["amount"] == cost
    assert params["description"] == description


def test_get_total_donations():
    """
    Tests that get_total_donations correctly queries and returns the sum.
    """
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_conn.__enter__().execute.return_value.scalar_one_or_none.return_value = Decimal("1000")
    repo = BudgetLedgerRepository(engine=mock_engine)

    total_donations = repo.get_total_donations()

    assert total_donations == Decimal("1000")
    mock_conn.__enter__().execute.assert_called_once()


def test_get_total_expenses_for_period():
    """
    Tests that get_total_expenses_for_period correctly queries and returns the sum.
    """
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value = mock_conn
    mock_conn.__enter__().execute.return_value.scalar_one_or_none.return_value = Decimal("500")
    repo = BudgetLedgerRepository(engine=mock_engine)

    total_expenses = repo.get_total_expenses_for_period(date(2025, 1, 1))

    assert total_expenses == Decimal("500")
    mock_conn.__enter__().execute.assert_called_once()
