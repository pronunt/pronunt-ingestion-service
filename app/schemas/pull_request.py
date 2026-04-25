from datetime import datetime

from pydantic import BaseModel, Field


class IngestionPullRequestPayload(BaseModel):
    repository_full_name: str = Field(..., examples=["pronunt/pronunt-aggregator-service"])
    repository_owner: str
    repository_name: str
    number: int = Field(..., ge=1)
    title: str
    author_username: str
    state: str = "open"
    review_status: str = "pending"
    is_draft: bool = False
    html_url: str | None = None
    base_branch: str
    head_branch: str
    labels: list[str] = Field(default_factory=list)
    changed_files: int = Field(default=0, ge=0)
    additions: int = Field(default=0, ge=0)
    deletions: int = Field(default=0, ge=0)
    criticality: str = "medium"
    created_at: datetime
    updated_at: datetime
    merged_at: datetime | None = None
    closed_at: datetime | None = None
    impact_services: list[str] = Field(default_factory=list)
    ai_summary: str | None = None


class IngestionEnqueueResult(BaseModel):
    status: str
    queue: str
    routing_key: str
    pr_uid: str


class IngestionDependencyResponse(BaseModel):
    status: str
    rabbitmq_url: str
    exchange: str
    routing_key: str
    queue: str
