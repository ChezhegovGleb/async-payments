import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import router
from app.outbox_publisher import publish_pending_events

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    stop_event = asyncio.Event()
    publisher_task = asyncio.create_task(publish_pending_events(stop_event))
    logger.info("Outbox publisher started")
    yield
    stop_event.set()
    await publisher_task
    logger.info("Outbox publisher stopped")


app = FastAPI(title="Async Payments", version="0.1.0", lifespan=lifespan)
app.include_router(router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
