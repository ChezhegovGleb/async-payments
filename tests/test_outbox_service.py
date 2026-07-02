from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.services.outbox_service import OutboxService


@pytest.mark.asyncio
async def test_outbox_service_marks_only_successfully_published_events(monkeypatch: pytest.MonkeyPatch) -> None:
    first_event = SimpleNamespace(id="1", payload={"event": 1}, published_at=None, created_at=datetime.now(UTC))
    second_event = SimpleNamespace(id="2", payload={"event": 2}, published_at=None, created_at=datetime.now(UTC))

    class _ScalarResult:
        def all(self) -> list[SimpleNamespace]:
            return [first_event, second_event]

    session = AsyncMock()
    session.execute.return_value = SimpleNamespace(scalars=lambda: _ScalarResult())

    publish_calls: list[dict] = []

    async def fake_publish(payload: dict) -> None:
        publish_calls.append(payload)
        if payload["event"] == 2:
            raise RuntimeError("publish failed")

    monkeypatch.setattr("app.services.outbox_service.publish_message", fake_publish)

    published_count = await OutboxService(session).publish_pending_events()

    assert published_count == 1
    assert first_event.published_at is not None
    assert second_event.published_at is None
    assert publish_calls == [{"event": 1}, {"event": 2}]
    assert session.commit.await_count == 1
    assert session.rollback.await_count == 1
