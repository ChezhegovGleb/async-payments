from unittest.mock import patch

import httpx
import pytest

from app.services.webhook_service import WebhookService


class _Response:
    def __init__(self, is_success: bool, status_code: int) -> None:
        self.is_success = is_success
        self.status_code = status_code


class _AsyncClientStub:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self._index = 0

    async def __aenter__(self) -> "_AsyncClientStub":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def post(self, url: str, json: dict) -> object:
        response = self._responses[self._index]
        self._index += 1
        if isinstance(response, Exception):
            raise response
        return response


@pytest.mark.asyncio
async def test_webhook_service_retries_with_exponential_backoff() -> None:
    sleep_calls: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        sleep_calls.append(seconds)

    client = _AsyncClientStub(
        [
            httpx.ConnectError("boom"),
            _Response(is_success=False, status_code=500),
            _Response(is_success=True, status_code=200),
        ]
    )

    with patch("app.services.webhook_service.httpx.AsyncClient", return_value=client):
        delivered = await WebhookService(sleep=fake_sleep).send_with_retries(
            url="https://example.com/webhook",
            payload={"payment_id": "1"},
        )

    assert delivered is True
    assert sleep_calls == [1.0, 2.0]
