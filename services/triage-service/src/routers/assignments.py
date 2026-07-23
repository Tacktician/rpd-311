"""GET /assignments/{reportId}."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from ..dependencies import require_service_token
from ..triage_ops import get_assignment_by_report

router = APIRouter(
    prefix="/assignments", tags=["Assignments"], dependencies=[Depends(require_service_token)]
)


@router.get("/{report_id}")
async def get_assignment(report_id: UUID):
    return await get_assignment_by_report(report_id)
