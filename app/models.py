import enum
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    String,
)
from sqlalchemy.orm import relationship

from .db import Base


class Country(enum.Enum):
    """Countries the service operates in (ISO 3166-1 alpha-2 codes)."""

    SN = "SN"  # Senegal
    CI = "CI"  # Côte d'Ivoire
    CM = "CM"  # Cameroon
    NE = "NE"  # Niger
    UG = "UG"  # Uganda


class TransferStatus(enum.Enum):
    """Lifecycle states a transfer can be in."""

    PENDING = "pending"
    COMPLETED = "completed"
    REVERSED = "reversed"
    FAILED = "failed"


class User(Base):
    """A wallet account holder who can send and receive transfers."""

    __tablename__ = "users"
    # A user's balance may never go negative: the database rejects any write
    # that would overdraw the account.
    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_users_balance_nonneg"),
    )

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    email_address = Column(String(50), nullable=False)
    mobile = Column(String, unique=True, nullable=False)
    country = Column(Enum(Country), nullable=False)
    balance = Column(Integer, nullable=False, default=0)  # minor units
    daily_send_limit = Column(Integer, nullable=False)  # minor units

    sent_transfers = relationship(
        "Transfer",
        foreign_keys="Transfer.sender_id",
        back_populates="sender",
    )

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        if self.daily_send_limit is None and self.country is not None:
            from .countries import COUNTRY_INFO

            self.daily_send_limit = COUNTRY_INFO[self.country].daily_send_limit


class Transfer(Base):
    """A single peer-to-peer money transfer between two users."""

    __tablename__ = "transfers"

    id = Column(Integer, primary_key=True)
    sender_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    recipient_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    amount = Column(Integer, nullable=False)  # minor units
    status = Column(
        Enum(TransferStatus), nullable=False, default=TransferStatus.PENDING
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    sender = relationship(
        "User", foreign_keys=[sender_id], back_populates="sent_transfers"
    )
    recipient = relationship("User", foreign_keys=[recipient_id])
