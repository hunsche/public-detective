"""
This module defines the Pydantic models for the budget ledger.
"""

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel


class TransactionType(StrEnum):
    """Enumeration for the types of budget transactions."""

    DONATION = "DONATION"
    EXPENSE = "EXPENSE"


class BudgetLedger(BaseModel):
    """Represents a single entry in the budget ledger.

    Attributes:
        id: The unique identifier for this ledger entry.
        transaction_type: The type of transaction (e.g., 'DONATION', 'EXPENSE').
        amount: The amount of the transaction.
        related_analysis_id: The ID of the analysis related to this transaction.
        related_donation_id: The ID of the donation related to this transaction.
        description: A description of the transaction.
        created_at: The timestamp of when the transaction was created.
    """

    id: UUID
    transaction_type: TransactionType
    amount: Decimal
    related_analysis_id: UUID | None = None
    related_donation_id: UUID | None = None
    description: str | None = None
    created_at: datetime
