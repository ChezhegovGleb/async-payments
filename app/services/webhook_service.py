import asyncio
import logging
from collections.abc import Awaitable, Callable

import httpx

from app.config import settings

logger = logging.getLogger(__name__)


SleepFunc = Callable[[float], Awaitable[None]]


class WebhookService:
    def __init__(self, *, sleep: SleepFunc = asyncio.sleep) -> None:
        self._sleep = sleep

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
                    await self._sleep(delay)
                    delay *= 2

        logger.error(
            "Webhook delivery failed after %s attempts for %s",
            settings.webhook_max_retries,
            url,
        )
        return False
