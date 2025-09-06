"""This module defines the repository for handling budget ledger operations."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import Engine, text


class BudgetLedgerRepository:
    """Handles all database operations related to the budget ledger."""

    def __init__(self, engine: Engine) -> None:
        """Initializes the repository with a database engine.

        Args:
            engine: The SQLAlchemy Engine to be used for all database
                communications.
        """
        self.engine = engine

    def save_expense(self, analysis_id: UUID, amount: Decimal, description: str) -> None:
        """Saves an expense to the budget ledger.

        Args:
            analysis_id: The ID of the analysis related to this expense.
            amount: The monetary value of the expense.
            description: A brief description of the expense.
        """
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
