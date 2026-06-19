from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/payments"
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672/"
    api_key: str = "dev-api-key-change-me"

    outbox_poll_interval_seconds: float = 1.0
    outbox_batch_size: int = 50

    webhook_max_retries: int = 3
    webhook_retry_base_delay_seconds: float = 1.0

    payment_queue: str = "payments.new"
    payment_dlq: str = "payments.new.dlq"
    payment_exchange: str = "payments"


settings = Settings()
