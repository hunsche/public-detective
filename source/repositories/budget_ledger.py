"""
This module defines the repository for handling budget ledger operations.
"""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, text


class BudgetLedgerRepository:
    """Handles all database operations related to the budget ledger."""

    def __init__(self, engine: Engine) -> None:
        """Initializes the repository with a database engine."""
        self.engine = engine

    def save_expense(self, analysis_id: UUID, amount: Decimal, description: str) -> None:
        """Saves an expense to the budget ledger."""
        sql = text(
            """
            INSERT INTO budget_ledgers (transaction_type, related_analysis_id, amount, description)
            VALUES ('EXPENSE', :analysis_id, :amount, :description)
            """
        )
        with self.engine.connect() as conn:
            conn.execute(
                sql,
                {
                    "analysis_id": analysis_id,
                    "amount": amount,
                    "description": description,
                },
            )
            conn.commit()
