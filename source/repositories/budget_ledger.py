"""
This module defines the repository for handling database operations
related to the budget ledger.
"""
from uuid import UUID

from models.budget_ledger import BudgetLedger, TransactionType
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

    def save_expense(self, analysis_id: UUID, cost: float, description: str) -> None:
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
