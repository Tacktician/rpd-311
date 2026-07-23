"""Outbound calls to reports-service.

Callbacks are best-effort: per CLAUDE.md, triage must not fail because the
status callback failed. Failures are logged and swallowed.
"""
from __future__ import annotations

import httpx

from .config import config
from .logging_conf import logger


async def update_report_status(
    report_id: str, status: str, outbound_headers: dict[str, str], note: str | None = None
) -> None:
    """PATCH reports-service /reports/{reportId}/status. Never raises."""
    payload: dict = {"status": status}
    if note:
        payload["note"] = note

    headers = {
        "content-type": "application/json",
        "x-service-token": config.service_token,
        **outbound_headers,
    }
    url = f"{config.reports_service_url}/reports/{report_id}/status"
    try:
        async with httpx.AsyncClient(timeout=config.callback_timeout_seconds) as client:
            resp = await client.patch(url, json=payload, headers=headers)
        if resp.status_code >= 400:
            logger.warning(
                "reports-service rejected status callback. Report left for reconciliation.",
                report_id=report_id,
                status=status,
                http_status=resp.status_code,
            )
        else:
            logger.info(
                f"Report {report_id} status callback -> {status} acknowledged by reports-service."
            )
    except httpx.HTTPError as exc:
        logger.warning(
            "reports-service unavailable for status callback. Assignment stands regardless.",
            report_id=report_id,
            status=status,
            error=str(exc),
        )


async def ping(outbound_headers: dict[str, str]) -> str:
    """Liveness probe for the health endpoint. Returns 'healthy' | 'unhealthy'."""
    # X-Health-Probe tells the peer to answer shallowly (local deps only), so peer
    # /health checks don't recurse into each other.
    headers = {"x-service-token": config.service_token, "x-health-probe": "1", **outbound_headers}
    url = f"{config.reports_service_url}/health"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(url, headers=headers)
        return "healthy" if resp.status_code < 500 else "unhealthy"
    except httpx.HTTPError:
        return "unhealthy"
