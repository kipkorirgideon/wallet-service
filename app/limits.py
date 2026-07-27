"""Daily send-limit enforcement for P2P transfers.

Each user has a daily send limit. This module computes how much a user has
already sent today and decides whether a new transfer is allowed.
"""

from datetime import datetime

from .models import TransferStatus
from .transfers import get_transfers


class LimitExceeded(Exception):
    def __init__(self, limit, already_sent):
        self.limit = limit
        self.already_sent = already_sent
        super().__init__(
            f"daily send limit of {limit} reached "
            f"(already sent {already_sent} today)"
        )


def _start_of_today():
    """Return the timestamp at which today's usage window begins.

    Transfers created before this point belong to a previous day and no longer
    count toward today's total.
    """
    now = datetime.utcnow()
    return datetime(now.year, now.month, now.day)


def _amount_sent_today(session, user):
    """Total the user has already sent today.

    Reversed transfers still count against the limit; failed and in-flight
    (pending) transfers don't.
    """
    # Calculate start of day
    start_of_day = _start_of_today()

    # Get all transfers for today
    todays_transfers = get_transfers(session, user, since=start_of_day)

    counted = [
        t
        for t in todays_transfers
        if t.status not in (TransferStatus.FAILED, TransferStatus.PENDING)
    ]

    # Sum all the transfer amounts up
    return sum(transfer.amount for transfer in counted)


def check_daily_limit(session, user, amount):
    """Raise ``LimitExceeded`` if sending ``amount`` would break the limit."""
    already_sent = _amount_sent_today(session, user)
    limit = user.daily_send_limit
    if already_sent + amount >= limit:
        raise LimitExceeded(limit=limit, already_sent=already_sent)
