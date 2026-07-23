"""Builds OpenAPI response shapes from asyncpg records.

asyncpg returns UUID and datetime objects; these helpers stringify them so the
JSON output matches the spec (uuid strings, ISO-8601 timestamps).
"""
from __future__ import annotations

from datetime import datetime


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value is not None else None


def routing_decision(assignment, departments) -> dict:
    immediate = bool(assignment["immediate_escalation"])
    # Primary department first for stable, readable output.
    ordered = sorted(departments, key=lambda d: (not d["is_primary"], d["department"]))
    return {
        "assignedSeverity": assignment["assigned_severity"],
        "departments": [
            {
                "department": d["department"],
                "isPrimary": d["is_primary"],
                "immediateEscalation": immediate and d["is_primary"],
            }
            for d in ordered
        ],
        "classificationReason": assignment["classification_reason"],
    }


def triage_response(assignment, departments) -> dict:
    return {
        "assignmentId": str(assignment["assignment_id"]),
        "reportId": str(assignment["report_id"]),
        "routing": routing_decision(assignment, departments),
        "status": assignment["status"],
        "triagedAt": _iso(assignment["triaged_at"]),
    }


def assignment_response(assignment, departments) -> dict:
    return {
        "assignmentId": str(assignment["assignment_id"]),
        "reportId": str(assignment["report_id"]),
        "routing": routing_decision(assignment, departments),
        "status": assignment["status"],
        "acknowledgedBy": assignment["acknowledged_by"],
        "acknowledgedAt": _iso(assignment["acknowledged_at"]),
        "triagedAt": _iso(assignment["triaged_at"]),
        "updatedAt": _iso(assignment["updated_at"]),
    }
