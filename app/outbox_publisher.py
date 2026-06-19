import asyncio
import logging

from sqlalchemy import select

from app.rabbitmq import publish_message
from app.config import settings
from app.database import async_session_factory
from app.models import OutboxEvent

logger = logging.getLogger(__name__)


async def publish_pending_events(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        async with async_session_factory() as session:
            result = await session.execute(
                select(OutboxEvent)
                .where(OutboxEvent.published_at.is_(None))
                .order_by(OutboxEvent.created_at)
                .limit(settings.outbox_batch_size)
            )
            events = result.scalars().all()

            for event in events:
                try:
                    await publish_message(event.payload)
                    from datetime import UTC, datetime

                    event.published_at = datetime.now(UTC)
                    await session.commit()
                    logger.info("Published outbox event %s", event.id)
                except Exception:
                    await session.rollback()
                    logger.exception("Failed to publish outbox event %s", event.id)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.outbox_poll_interval_seconds)
        except TimeoutError:
            continue
