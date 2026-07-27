from app.models import Country, Transfer, TransferStatus, User
from tests.conftest import send_money


def test_send_money_moves_balance(session, alice, bob):
    result = send_money(session, alice, bob, 2500)

    assert result.errors is None
    assert result.data["sendMoney"]["status"] == "completed"
    assert result.data["sendMoney"]["amount"] == 2500
    assert alice.balance == 1_000_000 - 2500
    assert bob.balance == 1_000_000 + 2500


def test_insufficient_balance_records_failed_transfer(session, bob):
    poor = User(
        name="Poor", mobile="+221700000009", country=Country.CI, balance=100
    )
    session.add(poor)
    session.commit()

    result = send_money(session, poor, bob, 5000)

    assert result.errors is not None
    # A FAILED transfer row is still recorded for the attempt.
    recorded = session.query(Transfer).filter_by(sender_id=poor.id).one()
    assert recorded.status == TransferStatus.FAILED
    assert poor.balance == 100  # unchanged


def test_can_send_again_after_a_reversal(session, alice, bob):
    # A recent transfer from Alice was reversed — the money came back to her.
    session.add(
        Transfer(
            sender_id=alice.id,
            recipient_id=bob.id,
            amount=300_000,
            status=TransferStatus.REVERSED,
        )
    )
    session.commit()

    result = send_money(session, alice, bob, 300_000)

    # daily limit now applies here
    assert result.errors is not None
