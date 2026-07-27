"""Transfer logic layer.

The business rules for moving money live here. Callers should go through
:func:`execute_transfer` rather than mutating balances or creating transfer rows directly.
"""

from datetime import datetime

from sqlalchemy import update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from .models import Transfer, TransferStatus, User


class TransferError(Exception):
    """Raised when a transfer cannot be completed."""


def get_transfers(
    session: Session, user: User, since: datetime | None = None
) -> list[Transfer]:
    """Get transfers made by a user, newest first.

    If ``since`` is given, only transfers created on or after it are returned.
    """
    query = session.query(Transfer).filter(Transfer.sender_id == user.id)
    if since is not None:
        query = query.filter(Transfer.created_at >= since)
    return query.order_by(Transfer.created_at.desc()).all()


def execute_transfer(
    session: Session, sender: User, recipient_id: int, amount: int
) -> Transfer:
    """Move ``amount`` from ``sender`` to ``recipient_id``.

    The transfer row is created ``PENDING`` and committed first, so the attempt
    is durable even if the money movement fails. We then debit the sender and
    credit the recipient; the ``users`` table has a ``balance >= 0`` check
    constraint, so an overdraw is rejected by the database. If any of the
    database writes fail, the transfer is marked ``FAILED``.
    """
    if amount <= 0:
        raise TransferError("amount must be positive")

    transfer = Transfer(
        sender_id=sender.id,
        recipient_id=recipient_id,
        amount=amount,
        status=TransferStatus.PENDING,
    )
    session.add(transfer)
    session.commit()

    try:
        session.execute(
            update(User)
            .where(User.id == sender.id)
            .values(balance=User.balance - amount)
        )
        session.execute(
            update(User)
            .where(User.id == recipient_id)
            .values(balance=User.balance + amount)
        )
        transfer.status = TransferStatus.COMPLETED
        session.commit()
    except SQLAlchemyError:
        session.rollback()
        transfer.status = TransferStatus.FAILED
        session.commit()
        raise TransferError("transfer failed")

    return transfer
