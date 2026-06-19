import asyncio
import logging
import random
from uuid import UUID

from faststream import FastStream
from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import settings
from app.database import async_session_factory
from app.models import PaymentStatus
from app.rabbitmq import DLX_NAME
from app.services import PaymentService, WebhookService

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CONSUMER_MAX_RETRIES = 3

broker = RabbitBroker(settings.rabbitmq_url)
app = FastStream(broker)

payment_queue = RabbitQueue(
    settings.payment_queue,
    durable=True,
    arguments={
        "x-dead-letter-exchange": DLX_NAME,
        "x-dead-letter-routing-key": settings.payment_dlq,
    },
)
payment_exchange = RabbitExchange(
    settings.payment_exchange,
    type=ExchangeType.DIRECT,
    durable=True,
)


async def handle_payment(message: dict) -> None:
    payment_id = UUID(message["payment_id"])

    delay = random.uniform(2, 5)
    logger.info("Processing payment %s (delay %.2fs)", payment_id, delay)
    await asyncio.sleep(delay)

    success = random.random() < 0.9
    status = PaymentStatus.SUCCEEDED if success else PaymentStatus.FAILED

    async with async_session_factory() as session:
        service = PaymentService(session)
        payment = await service.update_status(payment_id, status)
        if payment is None:
            raise ValueError(f"Payment {payment_id} not found")

    webhook_payload = {
        "payment_id": str(payment.id),
        "status": payment.status.value,
        "amount": str(payment.amount),
        "currency": payment.currency.value,
        "processed_at": payment.processed_at.isoformat() if payment.processed_at else None,
    }

    webhook_service = WebhookService()
    delivered = await webhook_service.send_with_retries(
        url=payment.webhook_url,
        payload=webhook_payload,
    )
    if not delivered:
        logger.error("Webhook delivery failed for payment %s", payment_id)

    logger.info("Payment %s processed with status %s", payment_id, status.value)


@broker.subscriber(payment_queue, payment_exchange)
async def process_payment(message: dict) -> None:
    delay_seconds = 1.0

    for attempt in range(1, CONSUMER_MAX_RETRIES + 1):
        try:
            await handle_payment(message)
            return
        except Exception:
            logger.exception(
                "Payment processing attempt %s/%s failed for message %s",
                attempt,
                CONSUMER_MAX_RETRIES,
                message,
            )
            if attempt == CONSUMER_MAX_RETRIES:
                raise

            await asyncio.sleep(delay_seconds)
            delay_seconds *= 2
