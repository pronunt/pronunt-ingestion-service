import asyncio
from datetime import UTC, datetime, timedelta

from fastapi import Request

from app.core.auth import AuthContext
from app.core.settings import Settings
from app.schemas.pull_request import IngestionPullRequestPayload
from app.services import ingestion as ingestion_service_module
from app.services.ingestion import IngestionService


class FakeExchange:
    def __init__(self) -> None:
        self.messages: list[tuple[object, str]] = []

    async def publish(self, message, routing_key: str) -> None:
        self.messages.append((message, routing_key))


class FakeQueue:
    def __init__(self) -> None:
        self.bindings: list[tuple[FakeExchange, str]] = []

    async def bind(self, exchange: FakeExchange, routing_key: str) -> None:
        self.bindings.append((exchange, routing_key))


class FakeChannel:
    def __init__(self) -> None:
        self.exchange = FakeExchange()
        self.queue = FakeQueue()

    async def declare_exchange(self, *args, **kwargs) -> FakeExchange:
        return self.exchange

    async def declare_queue(self, *args, **kwargs) -> FakeQueue:
        return self.queue


class FakeConnection:
    def __init__(self) -> None:
        self.channel_instance = FakeChannel()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    async def channel(self) -> FakeChannel:
        return self.channel_instance


def _build_payload() -> IngestionPullRequestPayload:
    now = datetime.now(UTC)
    return IngestionPullRequestPayload(
        repository_full_name="pronunt/pronunt-aggregator-service",
        repository_owner="pronunt",
        repository_name="pronunt-aggregator-service",
        number=11,
        title="Queue PR into worker",
        author_username="sowrabh0-0",
        base_branch="main",
        head_branch="feat/queue-flow",
        labels=["ingestion"],
        changed_files=3,
        additions=25,
        deletions=5,
        created_at=now - timedelta(days=1),
        updated_at=now - timedelta(hours=1),
    )


def test_publish_pull_request_enqueues_message() -> None:
    fake_connection = FakeConnection()

    async def fake_connect_robust(*args, **kwargs):
        return fake_connection

    original_connect_robust = ingestion_service_module.aio_pika.connect_robust
    ingestion_service_module.aio_pika.connect_robust = fake_connect_robust
    try:
        service = IngestionService(Settings(_env_file=None, allow_unsafe_dev_auth=True))
        scope = {"type": "http", "headers": [(b"x-request-id", b"test-request-id")], "state": {}}
        request = Request(scope)
        auth_context = AuthContext(subject="dev-user", username="dev-user", roles=["developer"], token="token")

        result = asyncio.run(service.publish_pull_request(_build_payload(), request, auth_context))

        assert result.status == "queued"
        assert result.queue == "pronunt.pull_requests.normalized"
        assert result.pr_uid.endswith("#11")
        assert fake_connection.channel_instance.exchange.messages
    finally:
        ingestion_service_module.aio_pika.connect_robust = original_connect_robust
