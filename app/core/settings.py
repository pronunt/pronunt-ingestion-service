from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "pronunt-service"
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    log_level: str = "INFO"
    log_use_colors: bool = True

    request_id_header: str = "X-Request-ID"
    http_timeout_seconds: float = 10.0
    rabbitmq_url: str = "amqp://guest:guest@rabbitmq:5672/"
    rabbitmq_exchange: str = "pronunt.events"
    rabbitmq_pr_routing_key: str = "pull_request.normalized"
    rabbitmq_pr_queue: str = "pronunt.pull_requests.normalized"
    github_api_url: str = "https://api.github.com"
    auth_service_url: str = "http://pronunt-auth-service:8000"
    internal_service_token: str | None = None

    auth_enabled: bool = False
    allow_unsafe_dev_auth: bool = True
    keycloak_issuer: str | None = None
    keycloak_audience: str = "pronunt-api"
    keycloak_jwks_url: str | None = None

    def validate_runtime(self) -> None:
        errors: list[str] = []
        secure_envs = {"test", "testing", "stage", "staging", "prod", "production"}

        if self.http_timeout_seconds <= 0:
            errors.append("HTTP_TIMEOUT_SECONDS must be greater than 0.")
        if not self.rabbitmq_url:
            errors.append("RABBITMQ_URL is required.")
        if not self.rabbitmq_exchange:
            errors.append("RABBITMQ_EXCHANGE is required.")
        if not self.rabbitmq_pr_routing_key:
            errors.append("RABBITMQ_PR_ROUTING_KEY is required.")
        if not self.rabbitmq_pr_queue:
            errors.append("RABBITMQ_PR_QUEUE is required.")
        if not self.github_api_url:
            errors.append("GITHUB_API_URL is required.")
        if not self.auth_service_url:
            errors.append("AUTH_SERVICE_URL is required.")
        if not self.internal_service_token:
            errors.append("INTERNAL_SERVICE_TOKEN is required.")

        if self.auth_enabled:
            if not self.keycloak_issuer:
                errors.append("KEYCLOAK_ISSUER is required when AUTH_ENABLED=true.")
            if not self.keycloak_jwks_url:
                errors.append("KEYCLOAK_JWKS_URL is required when AUTH_ENABLED=true.")

        if self.app_env.lower() in secure_envs and self.allow_unsafe_dev_auth:
            errors.append("ALLOW_UNSAFE_DEV_AUTH must be false outside local development.")

        if errors:
            raise ValueError(" ".join(errors))


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
