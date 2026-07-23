"""POST /triage and POST /triage/batch."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status
from fastapi.responses import JSONResponse

from ..dependencies import require_service_token
from ..errors import AppError
from ..middleware import outbound_headers
from ..routing import batch_priority_key
from ..schemas import BatchRequest, TriageRequest
from ..triage_ops import triage_one

router = APIRouter(prefix="/triage", tags=["Triage"], dependencies=[Depends(require_service_token)])


@router.post("", status_code=status.HTTP_201_CREATED)
async def triage_report(req: TriageRequest, request: Request):
    return await triage_one(req, outbound_headers(request))


@router.post("/batch", status_code=status.HTTP_207_MULTI_STATUS)
async def triage_report_batch(batch: BatchRequest, request: Request):
    headers = outbound_headers(request)

    # ZOMBIE_SIGHTING / UMBRELLA_CORP_ACTIVITY are processed first, regardless of
    # their position in the request body.
    ordered = sorted(batch.reports, key=lambda r: batch_priority_key(r.type.value))

    results: list[dict] = []
    processed = 0
    failed = 0
    for req in ordered:
        try:
            assignment = await triage_one(req, headers)
            results.append({"reportId": str(req.report_id), "success": True, "assignment": assignment})
            processed += 1
        except AppError as exc:
            results.append(
                {
                    "reportId": str(req.report_id),
                    "success": False,
                    "error": {
                        "error": exc.code,
                        "message": exc.message,
                        "requestId": request.state.request_id,
                        "details": exc.details,
                    },
                }
            )
            failed += 1

    return JSONResponse(
        status_code=status.HTTP_207_MULTI_STATUS,
        content={"processed": processed, "failed": failed, "results": results},
    )
