import unittest
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

from repositories.budget_ledger import BudgetLedgerRepository


class TestBudgetLedgerRepository(unittest.TestCase):
    def setUp(self):
        self.mock_engine = MagicMock()
        self.mock_conn = self.mock_engine.connect.return_value.__enter__.return_value
        self.repo = BudgetLedgerRepository(self.mock_engine)

    def test_save_expense(self):
        # Arrange
        analysis_id = uuid4()
        amount = Decimal("123.45")
        description = "Test expense"

        # Act
        self.repo.save_expense(analysis_id, amount, description)

        # Assert
        self.mock_conn.execute.assert_called_once()
        self.mock_conn.commit.assert_called_once()

        # Check the SQL statement and parameters
        executed_sql = self.mock_conn.execute.call_args[0][0]
        params = self.mock_conn.execute.call_args[0][1]

        self.assertIn("INSERT INTO budget_ledgers", str(executed_sql))
        self.assertEqual(params["analysis_id"], analysis_id)
        self.assertEqual(params["amount"], amount)
        self.assertEqual(params["description"], description)
