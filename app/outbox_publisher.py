import asyncio
import logging

from app.config import settings
from app.database import async_session_factory
from app.services import OutboxService

logger = logging.getLogger(__name__)


async def publish_pending_events(stop_event: asyncio.Event) -> None:
    while not stop_event.is_set():
        async with async_session_factory() as session:
            published_count = await OutboxService(session).publish_pending_events()
            if published_count:
                logger.info("Published %s pending outbox event(s)", published_count)

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=settings.outbox_poll_interval_seconds)
        except TimeoutError:
            continue
