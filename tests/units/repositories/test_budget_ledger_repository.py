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
