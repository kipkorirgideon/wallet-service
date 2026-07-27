import datetime

import strawberry
from graphql import GraphQLError

from .auth import get_authenticated_user
from .countries import COUNTRY_INFO
from . import limits
from .models import Transfer
from .transfers import TransferError, get_transfers, execute_transfer


@strawberry.type
class TransferType:
    """GraphQL view of a transfer, mirroring the ``Transfer`` model."""

    id: int
    sender_id: int
    recipient_id: int
    amount: int
    status: str
    created_at: datetime.datetime

    @classmethod
    def from_model(cls, transfer: Transfer) -> "TransferType":
        """Build a ``TransferType`` from a ``Transfer`` ORM row."""
        return cls(
            id=transfer.id,
            sender_id=transfer.sender_id,
            recipient_id=transfer.recipient_id,
            amount=transfer.amount,
            status=transfer.status.value,
            created_at=transfer.created_at,
        )


@strawberry.type
class AccountInfo:
    """Account-level details for the current user."""

    country: str
    currency: str


@strawberry.type
class DailyLimitStatus:
    limit: int
    sent_today: int
    remaining: int
    # Fraction of the daily limit already used, in [0.0, 1.0]. The mobile app
    # renders this as a progress bar.
    used_fraction: float


@strawberry.type
class Query:
    """Read-only queries."""

    @strawberry.field
    def transactions(self, info: strawberry.Info) -> list[TransferType]:
        """Return the current user's transfers, newest first."""
        session = info.context["session"]
        user = get_authenticated_user(info)
        transfers = get_transfers(session, user)
        return [TransferType.from_model(t) for t in transfers]

    @strawberry.field
    def account(self, info: strawberry.Info) -> AccountInfo:
        """Return the current user's account info (country and currency)."""
        user = get_authenticated_user(info)
        country_info = COUNTRY_INFO[user.country]
        return AccountInfo(country=user.country.value, currency=country_info.currency)

    @strawberry.field
    def daily_limit_status(self, info: strawberry.Info) -> DailyLimitStatus:
        # the mobile team asked for this so users can see their remaining
        # headroom before they try to send
        session = info.context["session"]
        u = get_authenticated_user(info)
        start_of_day = limits._start_of_today()
        sent = sum(t.amount for t in get_transfers(session, u, since=start_of_day))
        limit = u.daily_send_limit
        return DailyLimitStatus(
            limit=limit,
            sent_today=sent,
            remaining=max(limit - sent, 0),
            used_fraction=sent / limit if limit else 0.0,
        )


@strawberry.type
class Mutation:
    """Mutations that move money or change state."""

    @strawberry.mutation
    def send_money(
        self, info: strawberry.Info, recipient_id: int, amount: int
    ) -> TransferType:
        """Send ``amount`` from the current user to ``recipient_id``."""
        session = info.context["session"]
        sender = get_authenticated_user(info)

        # Enforce the sender's daily send limit before moving any money.
        try:
            limits.check_daily_limit(session, sender, amount)
        except limits.LimitExceeded as exc:
            raise GraphQLError(str(exc))

        try:
            transfer = execute_transfer(session, sender, recipient_id, amount)
        except TransferError as exc:
            raise GraphQLError(str(exc))

        return TransferType.from_model(transfer)


schema = strawberry.Schema(query=Query, mutation=Mutation)
