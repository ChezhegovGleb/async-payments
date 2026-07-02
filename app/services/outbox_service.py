import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import OutboxEvent
from app.rabbitmq import publish_message

logger = logging.getLogger(__name__)


class OutboxService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def publish_pending_events(self) -> int:
        result = await self.session.execute(
            select(OutboxEvent)
            .where(OutboxEvent.published_at.is_(None))
            .order_by(OutboxEvent.created_at)
            .limit(settings.outbox_batch_size)
        )
        events = result.scalars().all()
        published_count = 0

        for event in events:
            try:
                await publish_message(event.payload)
                event.published_at = datetime.now(UTC)
                await self.session.commit()
                published_count += 1
                logger.info("Published outbox event %s", event.id)
            except Exception:
                await self.session.rollback()
                logger.exception("Failed to publish outbox event %s", event.id)

        return published_count
