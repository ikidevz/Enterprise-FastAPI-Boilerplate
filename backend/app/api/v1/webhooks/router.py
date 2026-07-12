from fastapi import APIRouter, Depends, HTTPException, Request, status
from typing import Any

from backend.application.webhooks.service import WebhookService
from backend.contracts.webhooks_contracts import (
    WebhookEndpointCreate,
    WebhookEndpointOut,
    WebhookDeliveryOut,
)
from backend.core.security.dependencies import get_current_active_user, get_db
from backend.domain.users.model import User
from backend.web.exceptions import NotFoundError, to_http_exception

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


@router.post("/endpoints", response_model=WebhookEndpointOut, status_code=status.HTTP_201_CREATED)
async def create_webhook_endpoint(
    request: Request,
    payload: WebhookEndpointCreate,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> WebhookEndpointOut:
    service = WebhookService(db)
    endpoint = await service.create_endpoint(current_user.id, payload.model_dump())
    return WebhookEndpointOut(
        id=endpoint.id,
        owner_id=endpoint.owner_id,
        name=endpoint.name,
        url=endpoint.url,
        subscribed_events=endpoint.subscribed_events,
        is_active=endpoint.is_active,
        created_at=endpoint.created_at,
    )


@router.get("/endpoints", response_model=list[WebhookEndpointOut])
async def list_webhook_endpoints(
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> list[WebhookEndpointOut]:
    service = WebhookService(db)
    endpoints = await service.list_endpoints(current_user.id)
    return [
        WebhookEndpointOut(
            id=endpoint.id,
            owner_id=endpoint.owner_id,
            name=endpoint.name,
            url=endpoint.url,
            subscribed_events=endpoint.subscribed_events,
            is_active=endpoint.is_active,
            created_at=endpoint.created_at,
        )
        for endpoint in endpoints
    ]


@router.delete("/endpoints/{endpoint_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_webhook_endpoint(
    endpoint_id: int,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> None:
    service = WebhookService(db)
    try:
        await service.revoke_endpoint(endpoint_id, current_user.id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/endpoints/{endpoint_id}/deliveries", response_model=list[WebhookDeliveryOut])
async def list_webhook_deliveries(
    endpoint_id: int,
    current_user: User = Depends(get_current_active_user),
    db=Depends(get_db),
) -> list[WebhookDeliveryOut]:
    service = WebhookService(db)
    deliveries = await service.list_deliveries(endpoint_id, current_user.id)
    return [
        WebhookDeliveryOut(
            id=delivery.id,
            endpoint_id=delivery.endpoint_id,
            event_type=delivery.event_type,
            payload=delivery.payload,
            attempt_count=delivery.attempt_count,
            last_attempt_at=delivery.last_attempt_at,
            last_status_code=delivery.last_status_code,
            delivered_at=delivery.delivered_at,
            created_at=delivery.created_at,
        )
        for delivery in deliveries
    ]
