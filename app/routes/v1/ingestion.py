from typing import Annotated

from fastapi import APIRouter, Depends, Request, status

from app.core.auth import AuthContext, require_roles
from app.core.settings import Settings, get_settings
from app.schemas.pull_request import (
    IngestionDependencyResponse,
    IngestionEnqueueResult,
    IngestionPullRequestPayload,
)
from app.services.ingestion import IngestionService

router = APIRouter(tags=["ingestion"])
IngestionAccessDependency = Annotated[
    AuthContext,
    Depends(require_roles("developer", "reviewer", "release")),
]


def get_ingestion_service(settings: Annotated[Settings, Depends(get_settings)]) -> IngestionService:
    return IngestionService(settings)


IngestionServiceDependency = Annotated[IngestionService, Depends(get_ingestion_service)]


@router.post("/prs/publish", status_code=status.HTTP_202_ACCEPTED)
async def publish_pull_request(
    payload: IngestionPullRequestPayload,
    request: Request,
    auth_context: IngestionAccessDependency,
    service: IngestionServiceDependency,
) -> IngestionEnqueueResult:
    return await service.publish_pull_request(payload, request, auth_context)


@router.get("/dependencies/queue")
def queue_dependency(
    settings: Annotated[Settings, Depends(get_settings)],
    _: IngestionAccessDependency,
) -> IngestionDependencyResponse:
    return IngestionDependencyResponse(
        status="configured",
        rabbitmq_url=settings.rabbitmq_url,
        exchange=settings.rabbitmq_exchange,
        routing_key=settings.rabbitmq_pr_routing_key,
        queue=settings.rabbitmq_pr_queue,
    )
