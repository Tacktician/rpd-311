"""Request-scoped middleware: request id + W3C trace propagation.

Reads `traceparent`/`tracestate` from the inbound request and stashes them on
request.state so every outbound httpx call can forward them. This is what populates
the Service Graph in Postman API Catalog — without it, triage-service appears as a
disconnected node even after discovery.
"""
from __future__ import annotations

from uuid import uuid4

from starlette.requests import Request
from starlette.middleware.base import BaseHTTPMiddleware

from .config import config


class ContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.request_id = str(uuid4())

        outbound: dict[str, str] = {}
        if config.traceparent_propagation_enabled:
            traceparent = request.headers.get("traceparent")
            if traceparent:
                outbound["traceparent"] = traceparent
                tracestate = request.headers.get("tracestate")
                if tracestate:
                    outbound["tracestate"] = tracestate
        request.state.outbound_headers = outbound

        response = await call_next(request)
        response.headers["X-Request-Id"] = request.state.request_id
        return response


def outbound_headers(request: Request) -> dict[str, str]:
    return getattr(request.state, "outbound_headers", {})
