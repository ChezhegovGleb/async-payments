import asyncio
import logging

from faststream import FastStream
from faststream.rabbit import ExchangeType, RabbitBroker, RabbitExchange, RabbitQueue

from app.config import settings
from app.rabbitmq import DLX_NAME
from app.services import PaymentProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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


@broker.subscriber(payment_queue, payment_exchange)
async def process_payment(message: dict) -> None:
    processor = PaymentProcessor()
    delay_seconds = settings.consumer_retry_base_delay_seconds

    for attempt in range(1, settings.consumer_max_retries + 1):
        try:
            await processor.process(message)
            return
        except Exception:
            logger.exception(
                "Payment processing attempt %s/%s failed for message %s",
                attempt,
                settings.consumer_max_retries,
                message,
            )
            if attempt == settings.consumer_max_retries:
                raise

            await asyncio.sleep(delay_seconds)
            delay_seconds *= 2
