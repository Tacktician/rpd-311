"""Shared FastAPI dependencies."""
from __future__ import annotations

from fastapi import Header

from .config import config
from .errors import unauthorized


async def require_service_token(x_service_token: str | None = Header(default=None)) -> None:
    """Validate the X-Service-Token header on every non-health endpoint.

    triage-service is internal only — resident JWTs are never accepted, and a
    missing or wrong token is rejected outright.
    """
    if not x_service_token or x_service_token != config.service_token:
        raise unauthorized(
            "Service token missing or invalid. triage-service is internal to the cluster."
        )
