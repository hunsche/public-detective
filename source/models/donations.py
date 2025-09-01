import uuid

from sqlalchemy import Column, DECIMAL, String, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.sql import func

from source.models.base import Base


class Donation(Base):
    __tablename__ = "donations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    donor_identifier = Column(String, nullable=False)
    amount = Column(DECIMAL(10, 2), nullable=False)
    transaction_id = Column(String)
    created_at = Column(TIMESTAMP(timezone=True), server_default=func.now())
