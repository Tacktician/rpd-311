"""GET /health — no auth. Used by K8s probes and the Postman Insights Agent."""
from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from .. import reports_client
from ..db import get_pool
from ..middleware import outbound_headers

router = APIRouter(tags=["Health"])


@router.get("/health")
async def health_check(request: Request):
    # Postgres is a hard dependency (down => 503). reports-service is soft: if only
    # the callback target is down we still serve (degraded, 200).
    postgres = "unhealthy"
    try:
        await get_pool().fetchval("SELECT 1")
        postgres = "healthy"
    except Exception:  # noqa: BLE001 - health must never raise
        postgres = "unhealthy"

    # A peer's health check sends X-Health-Probe; answer shallowly (skip the
    # reports-service ping) so mutual /health checks don't recurse into each other.
    if "x-health-probe" in request.headers:
        reports_service = "unknown"
    else:
        reports_service = await reports_client.ping(outbound_headers(request))

    if postgres != "healthy":
        overall, code = "unhealthy", 503
    elif reports_service != "healthy":
        overall, code = "degraded", 200
    else:
        overall, code = "healthy", 200

    return JSONResponse(
        status_code=code,
        content={
            "status": overall,
            "service": "triage-service",
            "version": "1.0.0",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dependencies": {"postgres": postgres, "reportsService": reports_service},
        },
    )
