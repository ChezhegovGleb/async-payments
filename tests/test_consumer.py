from unittest.mock import AsyncMock

import pytest

from app import consumer


@pytest.mark.asyncio
async def test_consumer_retries_with_exponential_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    sleep_calls: list[float] = []
    attempts = {"count": 0}

    class _Processor:
        async def process(self, message: dict) -> None:
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise RuntimeError("temporary")

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    monkeypatch.setattr(consumer, "PaymentProcessor", _Processor)
    monkeypatch.setattr(consumer.asyncio, "sleep", fake_sleep)

    await consumer.process_payment({"payment_id": "08d50cc0-3b39-4ffd-8a2b-2ab12de79f00"})

    assert attempts["count"] == 3
    assert sleep_calls == [1.0, 2.0]


@pytest.mark.asyncio
async def test_consumer_raises_after_max_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_sleep(seconds: float) -> None:
        return None

    class _Processor:
        async def process(self, message: dict) -> None:
            raise RuntimeError("always fails")

    monkeypatch.setattr(consumer, "PaymentProcessor", _Processor)
    monkeypatch.setattr(consumer.asyncio, "sleep", fake_sleep)

    with pytest.raises(RuntimeError, match="always fails"):
        await consumer.process_payment({"payment_id": "08d50cc0-3b39-4ffd-8a2b-2ab12de79f00"})
