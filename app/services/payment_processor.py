import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from uuid import UUID

from app.database import async_session_factory
from app.models import PaymentStatus
from app.services.payment_service import PaymentService
from app.services.webhook_service import WebhookService

logger = logging.getLogger(__name__)


SleepFunc = Callable[[float], Awaitable[None]]
RandomFloatFunc = Callable[[float, float], float]
RandomBoolFunc = Callable[[], float]


class PaymentProcessor:
    def __init__(
        self,
        *,
        webhook_service: WebhookService | None = None,
        sleep: SleepFunc = asyncio.sleep,
        random_delay: RandomFloatFunc = random.uniform,
        random_outcome: RandomBoolFunc = random.random,
    ) -> None:
        self._webhook_service = webhook_service or WebhookService()
        self._sleep = sleep
        self._random_delay = random_delay
        self._random_outcome = random_outcome

    async def process(self, message: dict) -> None:
        payment_id = UUID(message["payment_id"])

        delay_seconds = self._random_delay(2, 5)
        logger.info("Processing payment %s (delay %.2fs)", payment_id, delay_seconds)
        await self._sleep(delay_seconds)

        status = (
            PaymentStatus.SUCCEEDED
            if self._random_outcome() < 0.9
            else PaymentStatus.FAILED
        )

        async with async_session_factory() as session:
            payment = await PaymentService(session).update_status(payment_id, status)
            if payment is None:
                raise ValueError(f"Payment {payment_id} not found")

        webhook_payload = {
            "payment_id": str(payment.id),
            "status": payment.status.value,
            "amount": str(payment.amount),
            "currency": payment.currency.value,
            "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
        }
        delivered = await self._webhook_service.send_with_retries(
            url=payment.webhook_url,
            payload=webhook_payload,
        )
        if not delivered:
            logger.error("Webhook delivery failed for payment %s", payment_id)

        logger.info("Payment %s processed with status %s", payment_id, status.value)
