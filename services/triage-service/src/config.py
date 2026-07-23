"""Central configuration, read from the environment.

Values are injected via Kubernetes (see k8s/base/) in-cluster, or
docker-compose.local.yml locally.
"""
import os


def _bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.lower() in ("1", "true", "yes", "on")


class Config:
    port: int = int(os.environ.get("PORT", "3002"))
    log_level: str = os.environ.get("LOG_LEVEL", "info")

    postgres_host: str = os.environ.get("POSTGRES_HOST", "localhost")
    postgres_port: int = int(os.environ.get("POSTGRES_PORT", "5432"))
    postgres_user: str = os.environ.get("POSTGRES_USER", "rpd311")
    postgres_password: str = os.environ.get("POSTGRES_PASSWORD", "changeme")
    postgres_db: str = os.environ.get("POSTGRES_DB_TRIAGE", "triage")

    service_token: str = os.environ.get("SERVICE_TOKEN", "")

    reports_service_url: str = os.environ.get(
        "REPORTS_SERVICE_URL", "http://reports-service:3001/v1"
    )

    traceparent_propagation_enabled: bool = _bool(
        os.environ.get("TRACEPARENT_PROPAGATION_ENABLED"), True
    )

    # Callback timeout to reports-service (seconds). Failures are logged, not fatal.
    callback_timeout_seconds: float = 5.0

    # Batch endpoint ceiling (mirrors the OpenAPI spec).
    max_batch_size: int = 50


config = Config()
