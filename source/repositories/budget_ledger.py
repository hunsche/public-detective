"""
This module defines the repository for handling database operations
related to the budget ledger.
"""

from datetime import date
from decimal import Decimal
from uuid import UUID

from models.budget_ledger import TransactionType
from providers.logging import Logger, LoggingProvider
from sqlalchemy import Engine, text


class BudgetLedgerRepository:
    """Handles all database operations for the budget ledger."""

    logger: Logger
    engine: Engine

    def __init__(self, engine: Engine) -> None:
        """Initializes the repository with a database engine."""
        self.logger = LoggingProvider().get_logger()
        self.engine = engine

    def save_expense(self, analysis_id: UUID, cost: Decimal, description: str) -> None:
        """Saves a new expense record to the budget ledger.

        Args:
            analysis_id: The ID of the analysis that incurred the expense.
            cost: The cost of the analysis.
            description: A description of the expense.
        """
        self.logger.info(f"Saving expense for analysis {analysis_id}.")
        sql = text(
            """
            INSERT INTO budget_ledgers (
                transaction_type, amount, related_analysis_id, description
            ) VALUES (
                :transaction_type, :amount, :related_analysis_id, :description
            );
            """
        )
        params = {
            "transaction_type": TransactionType.EXPENSE.value,
            "amount": cost,
            "related_analysis_id": analysis_id,
            "description": description,
        }
        with self.engine.connect() as conn:
            conn.execute(sql, params)
            conn.commit()
        self.logger.info(f"Expense for analysis {analysis_id} saved successfully.")

    def get_total_donations(self) -> Decimal:
        """Calculates the sum of all donation amounts."""
        sql = text("SELECT COALESCE(SUM(amount), 0) FROM donations")
        with self.engine.connect() as conn:
            result = conn.execute(sql).scalar_one_or_none()
        return result or Decimal("0")

    def get_total_expenses_for_period(self, start_date: date) -> Decimal:
        """Calculates the sum of all expenses from a given start date."""
        sql = text(
            "SELECT COALESCE(SUM(amount), 0) FROM budget_ledgers "
            "WHERE transaction_type = 'EXPENSE' AND created_at >= :start_date"
        )
        with self.engine.connect() as conn:
            result = conn.execute(sql, {"start_date": start_date}).scalar_one_or_none()
        return result or Decimal("0")
