"""Database-backed triage operations.

Kept separate from the routers so both POST /triage and POST /triage/batch share
one code path. Each operation acquires its own connection/transaction so a failure
in one batch item never rolls back another.
"""
from __future__ import annotations

from uuid import UUID

import asyncpg

from .db import get_pool
from .errors import conflict, not_found
from .logging_conf import logger
from .reports_client import update_report_status
from .routing import classify
from .schemas import AcknowledgeRequest, TriageRequest
from .serialize import assignment_response, triage_response

_SEVERITY_ORDER = (
    "CASE a.assigned_severity "
    "WHEN 'CRITICAL' THEN 0 WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 WHEN 'LOW' THEN 3 END"
)


async def _load_departments(conn, assignment_id):
    return await conn.fetch(
        "SELECT department, is_primary FROM assignment_departments WHERE assignment_id = $1",
        assignment_id,
    )


async def _insert_assignment(conn, req: TriageRequest):
    decision = classify(req.type.value)
    # Immediate-escalation reports bypass the department queue: they start ESCALATED.
    status = "ESCALATED" if decision["immediateEscalation"] else "PENDING"

    async with conn.transaction():
        try:
            assignment = await conn.fetchrow(
                """INSERT INTO assignments
                     (report_id, assigned_severity, classification_reason, immediate_escalation, status)
                   VALUES ($1, $2, $3, $4, $5)
                   RETURNING *""",
                req.report_id,
                decision["assignedSeverity"],
                decision["classificationReason"],
                decision["immediateEscalation"],
                status,
            )
        except asyncpg.UniqueViolationError:
            # report_id is UNIQUE — a second triage of the same report is a conflict.
            raise conflict(
                "ALREADY_TRIAGED", f"Report {req.report_id} has already been assigned."
            )

        for dept in decision["departments"]:
            await conn.execute(
                "INSERT INTO assignment_departments (assignment_id, department, is_primary) VALUES ($1, $2, $3)",
                assignment["assignment_id"],
                dept["department"],
                dept["isPrimary"],
            )

        await conn.execute(
            "INSERT INTO routing_log (assignment_id, event, detail) VALUES ($1, 'TRIAGED', $2)",
            assignment["assignment_id"],
            decision["classificationReason"],
        )
        if decision["immediateEscalation"]:
            await conn.execute(
                "INSERT INTO routing_log (assignment_id, event, detail) VALUES ($1, 'ESCALATED', $2)",
                assignment["assignment_id"],
                "Immediate escalation. STARS Unit notified directly. Queue bypassed.",
            )

    departments = await _load_departments(conn, assignment["assignment_id"])
    return assignment, departments


async def triage_one(req: TriageRequest, outbound_headers: dict[str, str]) -> dict:
    """Classify + persist a single report, then fire the reports-service callback.

    Raises AppError(409) if the report was already triaged.
    """
    pool = get_pool()
    async with pool.acquire() as conn:
        assignment, departments = await _insert_assignment(conn, req)

    logger.info(
        f"Report {req.report_id} triaged as {assignment['assigned_severity']}.",
        assignment_id=str(assignment["assignment_id"]),
    )
    # Best-effort status callback — does not block or fail the triage decision.
    # Immediate-escalation reports (UMBRELLA_CORP_ACTIVITY) are pushed straight to
    # ESCALATED so the public status reflects the escalation; others go to TRIAGED.
    callback_status = "ESCALATED" if assignment["immediate_escalation"] else "TRIAGED"
    await update_report_status(str(req.report_id), callback_status, outbound_headers)
    return triage_response(assignment, departments)


async def get_assignment_by_report(report_id: UUID) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        assignment = await conn.fetchrow(
            "SELECT * FROM assignments WHERE report_id = $1", report_id
        )
        if assignment is None:
            raise not_found(
                "ASSIGNMENT_NOT_FOUND",
                f"No triage assignment exists for report {report_id}. "
                "The report may not yet have been triaged.",
            )
        departments = await _load_departments(conn, assignment["assignment_id"])
    return assignment_response(assignment, departments)


async def get_department_queue(
    department: str,
    status: str | None,
    severity: str | None,
    limit: int,
    offset: int,
) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        where = ["ad.department = $1"]
        params: list = [department]
        if status is not None:
            params.append(status)
            where.append(f"a.status = ${len(params)}")
        if severity is not None:
            params.append(severity)
            where.append(f"a.assigned_severity = ${len(params)}")
        where_sql = " AND ".join(where)
        from_sql = (
            "FROM assignments a "
            "JOIN assignment_departments ad ON ad.assignment_id = a.assignment_id "
            f"WHERE {where_sql}"
        )

        total = await conn.fetchval(f"SELECT count(*) {from_sql}", *params)

        # criticalCount ignores any severity filter — it always reports CRITICAL pressure.
        crit_where = ["ad.department = $1"]
        crit_params: list = [department]
        if status is not None:
            crit_params.append(status)
            crit_where.append(f"a.status = ${len(crit_params)}")
        crit_params.append("CRITICAL")
        crit_where.append(f"a.assigned_severity = ${len(crit_params)}")
        critical_count = await conn.fetchval(
            "SELECT count(*) FROM assignments a "
            "JOIN assignment_departments ad ON ad.assignment_id = a.assignment_id "
            f"WHERE {' AND '.join(crit_where)}",
            *crit_params,
        )

        params.append(limit)
        limit_idx = len(params)
        params.append(offset)
        offset_idx = len(params)
        rows = await conn.fetch(
            f"SELECT a.* {from_sql} "
            f"ORDER BY {_SEVERITY_ORDER}, a.triaged_at ASC "
            f"LIMIT ${limit_idx} OFFSET ${offset_idx}",
            *params,
        )

        dept_map: dict = {}
        if rows:
            ids = [r["assignment_id"] for r in rows]
            drows = await conn.fetch(
                "SELECT assignment_id, department, is_primary "
                "FROM assignment_departments WHERE assignment_id = ANY($1::uuid[])",
                ids,
            )
            for dr in drows:
                dept_map.setdefault(dr["assignment_id"], []).append(dr)

    return {
        "department": department,
        "assignments": [assignment_response(r, dept_map.get(r["assignment_id"], [])) for r in rows],
        "total": total,
        "criticalCount": critical_count,
        "limit": limit,
        "offset": offset,
    }


async def acknowledge_assignment(
    department: str,
    assignment_id: UUID,
    body: AcknowledgeRequest,
    outbound_headers: dict[str, str],
) -> dict:
    pool = get_pool()
    async with pool.acquire() as conn:
        assignment = await conn.fetchrow(
            "SELECT * FROM assignments WHERE assignment_id = $1", assignment_id
        )
        if assignment is None:
            raise not_found("ASSIGNMENT_NOT_FOUND", f"No assignment on file with id {assignment_id}.")

        routed = await conn.fetchval(
            "SELECT 1 FROM assignment_departments WHERE assignment_id = $1 AND department = $2",
            assignment_id,
            department,
        )
        if routed is None:
            raise not_found(
                "ASSIGNMENT_NOT_FOUND",
                f"Assignment {assignment_id} is not routed to {department}.",
            )

        if assignment["status"] != "PENDING":
            raise conflict(
                "ALREADY_ACKNOWLEDGED",
                f"Assignment {assignment_id} is already {assignment['status']} and cannot be acknowledged.",
            )

        async with conn.transaction():
            updated = await conn.fetchrow(
                """UPDATE assignments
                     SET status = 'ACKNOWLEDGED', acknowledged_by = $1,
                         acknowledged_at = NOW(), updated_at = NOW()
                   WHERE assignment_id = $2
                   RETURNING *""",
                body.acknowledged_by,
                assignment_id,
            )
            await conn.execute(
                "INSERT INTO routing_log (assignment_id, event, detail) VALUES ($1, 'ACKNOWLEDGED', $2)",
                assignment_id,
                body.note,
            )
        departments = await _load_departments(conn, assignment_id)

    await update_report_status(
        str(updated["report_id"]), "IN_PROGRESS", outbound_headers, note=body.note
    )
    return assignment_response(updated, departments)
