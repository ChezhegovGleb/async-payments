import asyncio
import logging
from datetime import UTC, datetime
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import OutboxEvent, Payment, PaymentStatus

logger = logging.getLogger(__name__)


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
        amount,
        currency,
        description: str,
        metadata: dict,
        webhook_url: str,
        idempotency_key: str,
    ) -> Payment:
        existing = await self.get_by_idempotency_key(idempotency_key)
        if existing:
            return existing

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

        outbox_event = OutboxEvent(
            event_type="payments.new",
            payload={
                "payment_id": str(payment.id),
                "amount": str(payment.amount),
                "currency": payment.currency.value,
                "webhook_url": payment.webhook_url,
            },
        )
        self.session.add(outbox_event)
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


class WebhookService:
    async def send_with_retries(self, *, url: str, payload: dict) -> bool:
        delay = settings.webhook_retry_base_delay_seconds

        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(1, settings.webhook_max_retries + 1):
                try:
                    response = await client.post(url, json=payload)
                    if response.is_success:
                        logger.info("Webhook delivered to %s on attempt %s", url, attempt)
                        return True
                    logger.warning(
                        "Webhook attempt %s failed for %s: HTTP %s",
                        attempt,
                        url,
                        response.status_code,
                    )
                except httpx.HTTPError as exc:
                    logger.warning("Webhook attempt %s failed for %s: %s", attempt, url, exc)

                if attempt < settings.webhook_max_retries:
                    await asyncio.sleep(delay)
                    delay *= 2

        logger.error("Webhook delivery failed after %s attempts for %s", settings.webhook_max_retries, url)
        return False
