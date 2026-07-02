from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Currency, OutboxEvent, Payment, PaymentStatus


class PaymentService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def get_by_id(self, payment_id: UUID) -> Payment | None:
        result = await self.session.execute(select(Payment).where(Payment.id == payment_id))
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(self, idempotency_key: str) -> Payment | None:
        result = await self.session.execute(
            select(Payment).where(Payment.idempotency_key == idempotency_key)
        )
        return result.scalar_one_or_none()

    async def create_payment(
        self,
        *,
        amount: Decimal,
        currency: Currency,
        description: str,
        metadata: dict,
        webhook_url: str,
        idempotency_key: str,
    ) -> Payment:
        existing_payment = await self.get_by_idempotency_key(idempotency_key)
        if existing_payment is not None:
            return existing_payment

        payment = Payment(
            amount=amount,
            currency=currency,
            description=description,
            metadata_=metadata,
            webhook_url=webhook_url,
            idempotency_key=idempotency_key,
            status=PaymentStatus.PENDING,
        )
        self.session.add(payment)
        await self.session.flush()

        self.session.add(
            OutboxEvent(
                event_type="payments.new",
                payload={
                    "payment_id": str(payment.id),
                    "amount": str(payment.amount),
                    "currency": payment.currency.value,
                    "webhook_url": payment.webhook_url,
                },
            )
        )
        await self.session.commit()
        await self.session.refresh(payment)
        return payment

    async def update_status(self, payment_id: UUID, status: PaymentStatus) -> Payment | None:
        payment = await self.get_by_id(payment_id)
        if payment is None:
            return None

        payment.status = status
        payment.processed_at = datetime.now(UTC)
        await self.session.commit()
        await self.session.refresh(payment)
        return payment
