"""GET /queue/{department} and POST /queue/{department}/assignments/{assignmentId}/acknowledge."""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request

from ..dependencies import require_service_token
from ..middleware import outbound_headers
from ..schemas import AcknowledgeRequest, AssignmentStatus, Department, SeverityLevel
from ..triage_ops import acknowledge_assignment, get_department_queue

router = APIRouter(prefix="/queue", tags=["Queue"], dependencies=[Depends(require_service_token)])


@router.get("/{department}")
async def get_queue(
    department: Department,
    status: AssignmentStatus | None = None,
    severity: SeverityLevel | None = None,
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    return await get_department_queue(
        department.value,
        status.value if status else None,
        severity.value if severity else None,
        limit,
        offset,
    )


@router.post("/{department}/assignments/{assignment_id}/acknowledge")
async def acknowledge(
    department: Department,
    assignment_id: UUID,
    body: AcknowledgeRequest,
    request: Request,
):
    return await acknowledge_assignment(
        department.value, assignment_id, body, outbound_headers(request)
    )
