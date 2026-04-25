import json
from datetime import datetime
from uuid import uuid4

import aio_pika
from fastapi import Request, status
import httpx

from app.core.auth import AuthContext, build_forward_headers
from app.core.http import service_request
from app.core.exceptions import AppException
from app.core.settings import Settings
from app.schemas.pull_request import (
    ConnectedRepositoryListResponse,
    ConnectedRepositoryResponse,
    IngestionEnqueueResult,
    IngestionPullRequestPayload,
    PullRequestSyncResult,
)


class IngestionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def publish_pull_request(
        self,
        payload: IngestionPullRequestPayload,
        request: Request,
        auth_context: AuthContext,
    ) -> IngestionEnqueueResult:
        await self._enqueue_payload(payload, request, auth_context)
        return IngestionEnqueueResult(
            status="queued",
            queue=self.settings.rabbitmq_pr_queue,
            routing_key=self.settings.rabbitmq_pr_routing_key,
            pr_uid=f"{payload.repository_full_name}#{payload.number}",
        )

    async def list_connected_repositories(
        self,
        request: Request,
        auth_context: AuthContext,
    ) -> ConnectedRepositoryListResponse:
        response = await service_request(
            "GET",
            f"{self.settings.auth_service_url}/api/v1/auth/github/repos",
            request=request,
            auth_context=auth_context,
        )
        items = [ConnectedRepositoryResponse.model_validate(item) for item in response.json()["items"]]
        return ConnectedRepositoryListResponse(items=items, total=len(items))

    async def sync_pull_requests(
        self,
        repository_owner: str,
        repository_name: str,
        request: Request,
        auth_context: AuthContext,
    ) -> PullRequestSyncResult:
        connection = await self._get_internal_connection(request, auth_context)
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {connection['access_token']}",
        }
        repository_full_name = f"{repository_owner}/{repository_name}"

        try:
            async with httpx.AsyncClient() as client:
                pulls_response = await client.get(
                    f"{self.settings.github_api_url}/repos/{repository_owner}/{repository_name}/pulls",
                    headers=headers,
                    params={"state": "open", "per_page": 100},
                    timeout=self.settings.http_timeout_seconds,
                )
                pulls_response.raise_for_status()
                pull_items = pulls_response.json()
        except httpx.HTTPStatusError as exc:
            raise AppException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                code="github_repository_fetch_failed",
                message="GitHub pull request listing failed.",
                details={
                    "repository_full_name": repository_full_name,
                    "github_status": exc.response.status_code,
                },
            ) from exc
        except httpx.HTTPError as exc:
            raise AppException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="github_unavailable",
                message="GitHub API is unavailable.",
                details={"repository_full_name": repository_full_name},
            ) from exc

        queued = 0
        async with httpx.AsyncClient() as client:
            for pull_item in pull_items:
                details_response = await client.get(
                    f"{self.settings.github_api_url}/repos/{repository_owner}/{repository_name}/pulls/{pull_item['number']}",
                    headers=headers,
                    timeout=self.settings.http_timeout_seconds,
                )
                details_response.raise_for_status()
                details = details_response.json()
                payload = self._build_payload(repository_owner, repository_name, details)
                await self._enqueue_payload(payload, request, auth_context)
                queued += 1

        return PullRequestSyncResult(
            status="queued",
            repository_full_name=repository_full_name,
            queued_pull_requests=queued,
        )

    async def _enqueue_payload(
        self,
        payload: IngestionPullRequestPayload,
        request: Request,
        auth_context: AuthContext,
    ) -> None:
        message_headers = build_forward_headers(request, auth_context)
        if self.settings.request_id_header not in message_headers:
            message_headers[self.settings.request_id_header] = str(uuid4())

        try:
            connection = await aio_pika.connect_robust(self.settings.rabbitmq_url)
            async with connection:
                channel = await connection.channel()
                exchange = await channel.declare_exchange(
                    self.settings.rabbitmq_exchange,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True,
                )
                queue = await channel.declare_queue(self.settings.rabbitmq_pr_queue, durable=True)
                await queue.bind(exchange, routing_key=self.settings.rabbitmq_pr_routing_key)

                body = payload.model_dump_json().encode("utf-8")
                message = aio_pika.Message(
                    body=body,
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    headers=message_headers,
                )
                await exchange.publish(message, routing_key=self.settings.rabbitmq_pr_routing_key)
        except aio_pika.AMQPException as exc:
            raise AppException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                code="queue_unavailable",
                message="RabbitMQ is unavailable.",
                details={"queue": self.settings.rabbitmq_pr_queue},
            ) from exc

    async def _get_internal_connection(self, request: Request, auth_context: AuthContext) -> dict:
        response = await service_request(
            "GET",
            f"{self.settings.auth_service_url}/api/v1/auth/internal/github-connection",
            request=request,
            auth_context=auth_context,
            headers={"X-Internal-Service-Token": self.settings.internal_service_token or ""},
        )
        return response.json()

    @staticmethod
    def _build_payload(
        repository_owner: str,
        repository_name: str,
        pull_request: dict,
    ) -> IngestionPullRequestPayload:
        labels = [label["name"] for label in pull_request.get("labels", [])]
        repository_full_name = f"{repository_owner}/{repository_name}"
        return IngestionPullRequestPayload(
            repository_full_name=repository_full_name,
            repository_owner=repository_owner,
            repository_name=repository_name,
            number=pull_request["number"],
            title=pull_request["title"],
            author_username=pull_request["user"]["login"],
            state=pull_request["state"],
            review_status="pending",
            is_draft=pull_request.get("draft", False),
            html_url=pull_request.get("html_url"),
            base_branch=pull_request["base"]["ref"],
            head_branch=pull_request["head"]["ref"],
            labels=labels,
            changed_files=pull_request.get("changed_files", 0),
            additions=pull_request.get("additions", 0),
            deletions=pull_request.get("deletions", 0),
            criticality="medium",
            created_at=datetime.fromisoformat(pull_request["created_at"].replace("Z", "+00:00")),
            updated_at=datetime.fromisoformat(pull_request["updated_at"].replace("Z", "+00:00")),
            merged_at=(
                datetime.fromisoformat(pull_request["merged_at"].replace("Z", "+00:00"))
                if pull_request.get("merged_at")
                else None
            ),
            closed_at=(
                datetime.fromisoformat(pull_request["closed_at"].replace("Z", "+00:00"))
                if pull_request.get("closed_at")
                else None
            ),
            impact_services=[],
            ai_summary=None,
        )
