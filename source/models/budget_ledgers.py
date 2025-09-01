import uuid

from sqlalchemy import Column, DECIMAL, Enum, ForeignKey, String, TIMESTAMP, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from source.models.base import Base


class BudgetLedger(Base):
    __tablename__ = "budget_ledgers"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    transaction_type = Column(Enum("DONATION", "EXPENSE", name="transaction_type_enum"), nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=False)
    related_analysis_id = Column(UUID(as_uuid=True), ForeignKey("procurement_analyses.analysis_id"))
    related_donation_id = Column(UUID(as_uuid=True), ForeignKey("donations.id"))
    description = Column(Text)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
