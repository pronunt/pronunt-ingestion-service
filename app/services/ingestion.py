import json
from uuid import uuid4

import aio_pika
from fastapi import Request, status

from app.core.auth import AuthContext, build_forward_headers
from app.core.exceptions import AppException
from app.core.settings import Settings
from app.schemas.pull_request import IngestionEnqueueResult, IngestionPullRequestPayload


class IngestionService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    async def publish_pull_request(
        self,
        payload: IngestionPullRequestPayload,
        request: Request,
        auth_context: AuthContext,
    ) -> IngestionEnqueueResult:
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

        return IngestionEnqueueResult(
            status="queued",
            queue=self.settings.rabbitmq_pr_queue,
            routing_key=self.settings.rabbitmq_pr_routing_key,
            pr_uid=f"{payload.repository_full_name}#{payload.number}",
        )
