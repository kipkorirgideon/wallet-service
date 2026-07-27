from app.models import Country, Transfer, TransferStatus, User
from app.schema import schema
from tests.conftest import context


def _send(session, sender, recipient, amount):
    return schema.execute_sync(
        "mutation { sendMoney(recipientId: %d, amount: %d) { amount } }"
        % (recipient.id, amount),
        context_value=context(session, sender),
    )


def test_transfer_allowed_under_daily_limit(session, alice, bob):
    alice.daily_send_limit = 10_000
    session.commit()

    result = _send(session, alice, bob, 3_000)

    assert result.errors is None
    assert result.data["sendMoney"]["amount"] == 3_000


def test_transfer_blocked_over_daily_limit(session, alice, bob):
    alice.daily_send_limit = 10_000
    session.commit()

    _send(session, alice, bob, 8_000)
    # 8,000 already sent + 5,000 more would exceed the 10,000 limit.
    result = _send(session, alice, bob, 5_000)

    assert result.errors is not None


def test_failed_transfer_does_not_count_toward_limit(session, alice, bob):
    alice.daily_send_limit = 10_000
    # A failed transfer earlier today (money never actually moved).
    session.add(
        Transfer(
            sender_id=alice.id,
            recipient_id=bob.id,
            amount=8_000,
            status=TransferStatus.FAILED,
        )
    )
    session.commit()

    # It should not eat into today's allowance.
    result = _send(session, alice, bob, 5_000)

    assert result.errors is None


def test_country_limit_applies(session, bob):
    # A Niger user gets Niger's daily limit.
    user = User(
        name="Ama", mobile="+22790000001", country=Country.NE, balance=10_000_000
    )
    session.add(user)
    session.commit()

    # NE's limit is 400,000, so sending 450,000 should be blocked.
    result = _send(session, user, bob, 450_000)

    assert result.errors is not None


def test_daily_limit_status_reports_usage(session, alice, bob):
    alice.daily_send_limit = 10_000
    session.commit()
    _send(session, alice, bob, 4_000)

    result = schema.execute_sync(
        "{ dailyLimitStatus { limit sentToday remaining usedFraction } }",
        context_value=context(session, alice),
    )

    assert result.errors is None
    status = result.data["dailyLimitStatus"]
    assert status["limit"] == 10_000
    assert status["sentToday"] == 4_000
    assert status["remaining"] == 6_000
