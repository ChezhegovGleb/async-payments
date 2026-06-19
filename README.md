# Async Payments

Микросервис для асинхронной обработки платежей: приём запросов, обработка через эмуляцию платёжного шлюза и уведомление клиента по webhook.

## Стек

- FastAPI + Pydantic v2
- SQLAlchemy 2.0 (async) + PostgreSQL
- RabbitMQ + FastStream (`faststream[rabbit,cli]`)
- Alembic
- Docker Compose

## Быстрый старт

```bash
docker compose up --build
```

Сервисы:

| Сервис   | URL                        |
|----------|----------------------------|
| API      | http://localhost:8000      |
| Swagger  | http://localhost:8000/docs |
| RabbitMQ | http://localhost:15672     |

API-ключ по умолчанию: `dev-api-key-change-me` (заголовок `X-API-Key`).

## API

### Создание платежа

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "Content-Type: application/json" \
  -H "X-API-Key: dev-api-key-change-me" \
  -H "Idempotency-Key: order-123" \
  -d '{
    "amount": "100.50",
    "currency": "RUB",
    "description": "Test payment",
    "metadata": {"order_id": "123"},
    "webhook_url": "https://webhook.site/your-unique-id"
  }'
```

Ответ `202 Accepted`:

```json
{
  "payment_id": "uuid",
  "status": "pending",
  "created_at": "2026-06-18T12:00:00Z"
}
```

Повторный запрос с тем же `Idempotency-Key` вернёт существующий платёж.

### Получение платежа

```bash
curl http://localhost:8000/api/v1/payments/{payment_id} \
  -H "X-API-Key: dev-api-key-change-me"
```

## Архитектура

```
Client → API → PostgreSQL (payments + outbox)
                ↓
         Outbox Publisher → RabbitMQ (payments.new)
                ↓
            Consumer → эмуляция шлюза (2–5 сек, 90% успех)
                ↓
         PostgreSQL (обновление статуса) → Webhook (retry × 3)
```

### Outbox pattern

Платёж и событие в таблице `outbox` сохраняются в одной транзакции. Фоновый publisher в API читает неопубликованные события и отправляет их в RabbitMQ.

### Retry и DLQ

- **Consumer**: до 3 попыток обработки с экспоненциальной задержкой; после финальной ошибки сообщение уходит в DLQ `payments.new.dlq`.
- **Webhook**: до 3 попыток доставки с экспоненциальной задержкой.

## Локальная разработка

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .

# PostgreSQL и RabbitMQ (через Docker)
docker compose up postgres rabbitmq -d

export DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/payments
export RABBITMQ_URL=amqp://guest:guest@localhost:5672/
export API_KEY=dev-api-key-change-me

alembic upgrade head
uvicorn app.main:app --reload
faststream run app.consumer:app
```

## Переменные окружения

| Переменная | Описание | По умолчанию |
|------------|----------|--------------|
| `DATABASE_URL` | PostgreSQL DSN | `postgresql+asyncpg://postgres:postgres@localhost:5432/payments` |
| `RABBITMQ_URL` | RabbitMQ URL | `amqp://guest:guest@localhost:5672/` |
| `API_KEY` | Статический API-ключ | `dev-api-key-change-me` |
