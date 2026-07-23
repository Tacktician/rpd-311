"""FastAPI application entrypoint (uvicorn src.main:app)."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from .config import config
from .db import close_pool, init_pool, migrate
from .errors import AppError
from .logging_conf import logger
from .middleware import ContextMiddleware
from .routers import assignments, health, queue, triage


@asynccontextmanager
async def lifespan(_app: FastAPI):
    await init_pool()
    await migrate()
    logger.info(f"RPD 311 Triage Service online. Reviewing incidents on port {config.port}.")
    yield
    await close_pool()
    logger.info("Triage Service shutting down. Dispatch board cleared.")


app = FastAPI(title="RPD 311 — Triage Service", version="1.0.0", lifespan=lifespan)
app.add_middleware(ContextMiddleware)

# Routers are mounted under /v1 to match the OpenAPI `servers` base path.
app.include_router(triage.router, prefix="/v1")
app.include_router(assignments.router, prefix="/v1")
app.include_router(queue.router, prefix="/v1")
app.include_router(health.router, prefix="/v1")


def _request_id(request: Request) -> str | None:
    return getattr(request.state, "request_id", None)


def _error_body(code: str, message: str, request_id: str | None, details: list | None = None):
    return {"error": code, "message": message, "requestId": request_id, "details": details or []}


@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message, _request_id(request), exc.details),
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    details = [
        {
            "field": ".".join(str(p) for p in err["loc"] if p not in ("body",)) or "(body)",
            "message": err["msg"],
        }
        for err in exc.errors()
    ]
    return JSONResponse(
        status_code=400,
        content=_error_body(
            "VALIDATION_ERROR",
            "The triage request did not pass validation. Please review the flagged fields.",
            _request_id(request),
            details,
        ),
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    logger.error(
        "Unhandled exception while processing request.",
        request_id=_request_id(request),
        error=str(exc),
    )
    return JSONResponse(
        status_code=500,
        content=_error_body(
            "INTERNAL_ERROR",
            "Dispatch encountered an unexpected condition. The incident has been logged.",
            _request_id(request),
        ),
    )
