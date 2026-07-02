from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest

from app.models import Currency, PaymentStatus
from app.services.payment_service import PaymentService


@pytest.mark.asyncio
async def test_create_payment_returns_existing_payment_for_same_idempotency_key() -> None:
    session = SimpleNamespace(
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
        flush=AsyncMock(),
    )
    service = PaymentService(session)
    existing_payment = SimpleNamespace(idempotency_key="same-key")
    service.get_by_idempotency_key = AsyncMock(return_value=existing_payment)

    payment = await service.create_payment(
        amount=Decimal("10.00"),
        currency=Currency.RUB,
        description="duplicate",
        metadata={},
        webhook_url="https://example.com/webhook",
        idempotency_key="same-key",
    )

    assert payment is existing_payment
    session.add.assert_not_called()
    session.commit.assert_not_called()


@pytest.mark.asyncio
async def test_create_payment_persists_payment_and_outbox_event() -> None:
    session = SimpleNamespace(
        add=Mock(),
        commit=AsyncMock(),
        refresh=AsyncMock(),
        flush=AsyncMock(),
    )
    service = PaymentService(session)
    service.get_by_idempotency_key = AsyncMock(return_value=None)

    async def flush_side_effect() -> None:
        payment = session.add.call_args_list[0].args[0]
        payment.id = "payment-id"

    session.flush.side_effect = flush_side_effect

    payment = await service.create_payment(
        amount=Decimal("10.00"),
        currency=Currency.USD,
        description="new payment",
        metadata={"order_id": "123"},
        webhook_url="https://example.com/webhook",
        idempotency_key="new-key",
    )

    assert payment.status == PaymentStatus.PENDING
    assert session.add.call_count == 2
    outbox_event = session.add.call_args_list[1].args[0]
    assert outbox_event.event_type == "payments.new"
    assert outbox_event.payload["payment_id"] == "payment-id"
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(payment)
