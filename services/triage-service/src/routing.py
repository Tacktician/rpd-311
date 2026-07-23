"""Triage classification engine.

The routing table and severity overrides are the heart of this service. Enum
values MUST match the OpenAPI spec exactly. Submitter-provided severity is always
discarded — triage classification is authoritative.
"""
from __future__ import annotations

# Ordered departments: index 0 is the primary (lead) department; the rest are
# secondary (cc) routing. immediateEscalation bypasses the queue entirely.
ROUTING_TABLE: dict[str, dict] = {
    "POTHOLE": {"severity": "LOW", "departments": ["PUBLIC_WORKS"]},
    "DOWNED_TREE": {"severity": "LOW", "departments": ["PUBLIC_WORKS"]},
    "NOISE_COMPLAINT": {"severity": "MEDIUM", "departments": ["RPD_NON_EMERGENCY"]},
    "SUSPICIOUS_PERSON": {"severity": "MEDIUM", "departments": ["RPD_NON_EMERGENCY"]},
    "VANDALISM": {"severity": "MEDIUM", "departments": ["RPD_NON_EMERGENCY", "SANITATION"]},
    "CAR_BREAK_IN": {"severity": "HIGH", "departments": ["RPD_EMERGENCY"]},
    "ZOMBIE_SIGHTING": {"severity": "CRITICAL", "departments": ["RPD_EMERGENCY", "STARS_UNIT"]},
    "UMBRELLA_CORP_ACTIVITY": {
        "severity": "CRITICAL",
        "departments": ["STARS_UNIT"],
        "immediateEscalation": True,
    },
}

# CRITICAL first. Used to order department queues and to prioritize batch processing.
SEVERITY_RANK = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}

# Types that jump the queue during batch processing, regardless of body order.
BATCH_PRIORITY_TYPES = {"ZOMBIE_SIGHTING", "UMBRELLA_CORP_ACTIVITY"}


def classify(incident_type: str) -> dict:
    """Return the routing decision for an incident type.

    Shape:
        {
          "assignedSeverity": str,
          "immediateEscalation": bool,
          "departments": [{"department": str, "isPrimary": bool, "immediateEscalation": bool}],
          "classificationReason": str,
        }
    """
    entry = ROUTING_TABLE[incident_type]
    severity = entry["severity"]
    immediate = bool(entry.get("immediateEscalation", False))
    dept_codes = entry["departments"]

    departments = [
        {
            "department": code,
            "isPrimary": index == 0,
            # Only the primary department of an immediate-escalation report bypasses the queue.
            "immediateEscalation": immediate and index == 0,
        }
        for index, code in enumerate(dept_codes)
    ]

    primary = dept_codes[0]
    reason = f"{incident_type} classified as {severity}. Primary routing to {primary}."
    if len(dept_codes) > 1:
        secondary = ", ".join(dept_codes[1:])
        reason += f" Secondary routing to {secondary} per standing protocol."
    if immediate:
        reason += " Immediate escalation: queue bypassed, STARS Unit notified directly."

    return {
        "assignedSeverity": severity,
        "immediateEscalation": immediate,
        "departments": departments,
        "classificationReason": reason,
    }


def batch_priority_key(incident_type: str) -> tuple[int, int]:
    """Sort key so CRITICAL escalation types are processed first in a batch."""
    priority = 0 if incident_type in BATCH_PRIORITY_TYPES else 1
    severity = ROUTING_TABLE.get(incident_type, {}).get("severity", "LOW")
    return (priority, SEVERITY_RANK.get(severity, 99))
