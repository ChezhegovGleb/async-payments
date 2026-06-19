from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_session
from app.schemas import CreatePaymentRequest, CreatePaymentResponse, PaymentResponse
from app.services import PaymentService

router = APIRouter(prefix="/api/v1/payments", tags=["payments"])


async def verify_api_key(x_api_key: str = Header(alias="X-API-Key")) -> None:
    from app.config import settings

    if x_api_key != settings.api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


@router.post(
    "",
    response_model=CreatePaymentResponse,
    status_code=status.HTTP_202_ACCEPTED,
    dependencies=[Depends(verify_api_key)],
)
async def create_payment(
    body: CreatePaymentRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
    session: AsyncSession = Depends(get_session),
) -> CreatePaymentResponse:
    if not idempotency_key.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Idempotency-Key header is required",
        )

    service = PaymentService(session)
    payment = await service.create_payment(
        amount=body.amount,
        currency=body.currency,
        description=body.description,
        metadata=body.metadata,
        webhook_url=str(body.webhook_url),
        idempotency_key=idempotency_key.strip(),
    )

    return CreatePaymentResponse(
        payment_id=payment.id,
        status=payment.status,
        created_at=payment.created_at,
    )


@router.get(
    "/{payment_id}",
    response_model=PaymentResponse,
    dependencies=[Depends(verify_api_key)],
)
async def get_payment(
    payment_id: str,
    session: AsyncSession = Depends(get_session),
) -> PaymentResponse:
    from uuid import UUID

    try:
        payment_uuid = UUID(payment_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found") from exc

    service = PaymentService(session)
    payment = await service.get_by_id(payment_uuid)
    if payment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")

    return PaymentResponse.model_validate(payment)
