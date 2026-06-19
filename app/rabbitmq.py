import json
import logging

import aio_pika

from app.config import settings

logger = logging.getLogger(__name__)

DLX_NAME = "payments.dlx"


async def setup_topology(channel: aio_pika.abc.AbstractChannel) -> aio_pika.Exchange:
    dlx = await channel.declare_exchange(DLX_NAME, aio_pika.ExchangeType.DIRECT, durable=True)
    main_exchange = await channel.declare_exchange(
        settings.payment_exchange, aio_pika.ExchangeType.DIRECT, durable=True
    )

    dlq = await channel.declare_queue(settings.payment_dlq, durable=True)
    await dlq.bind(dlx, routing_key=settings.payment_dlq)

    main_queue = await channel.declare_queue(
        settings.payment_queue,
        durable=True,
        arguments={
            "x-dead-letter-exchange": DLX_NAME,
            "x-dead-letter-routing-key": settings.payment_dlq,
        },
    )
    await main_queue.bind(main_exchange, routing_key=settings.payment_queue)

    logger.info("RabbitMQ topology declared")
    return main_exchange


async def publish_message(payload: dict) -> None:
    connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    async with connection:
        channel = await connection.channel()
        exchange = await setup_topology(channel)
        body = json.dumps(payload).encode()
        await exchange.publish(
            aio_pika.Message(body=body, delivery_mode=aio_pika.DeliveryMode.PERSISTENT),
            routing_key=settings.payment_queue,
        )
