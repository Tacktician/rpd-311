"""Pydantic request models. Response bodies are built as plain dicts in
serialize.py to keep full control over shape and timestamp formatting.

Incoming JSON is camelCase (reportId, submitterSeverity, ...); models declare
snake_case fields with a camelCase alias generator. extra='forbid' rejects
unknown fields, mirroring reports-service strict validation.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class IncidentType(str, Enum):
    POTHOLE = "POTHOLE"
    DOWNED_TREE = "DOWNED_TREE"
    NOISE_COMPLAINT = "NOISE_COMPLAINT"
    SUSPICIOUS_PERSON = "SUSPICIOUS_PERSON"
    VANDALISM = "VANDALISM"
    CAR_BREAK_IN = "CAR_BREAK_IN"
    ZOMBIE_SIGHTING = "ZOMBIE_SIGHTING"
    UMBRELLA_CORP_ACTIVITY = "UMBRELLA_CORP_ACTIVITY"


class SeverityLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class Department(str, Enum):
    PUBLIC_WORKS = "PUBLIC_WORKS"
    RPD_NON_EMERGENCY = "RPD_NON_EMERGENCY"
    RPD_EMERGENCY = "RPD_EMERGENCY"
    SANITATION = "SANITATION"
    STARS_UNIT = "STARS_UNIT"


class AssignmentStatus(str, Enum):
    PENDING = "PENDING"
    ACKNOWLEDGED = "ACKNOWLEDGED"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"
    ESCALATED = "ESCALATED"


class _Model(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True, extra="forbid")


class Location(_Model):
    lat: float = Field(ge=-90, le=90)
    lng: float = Field(ge=-180, le=180)
    address: str | None = Field(default=None, max_length=500)


class TriageRequest(_Model):
    report_id: UUID
    type: IncidentType
    description: str = Field(max_length=2000)
    location: Location
    submitter_severity: SeverityLevel | None = None
    received_at: datetime


class BatchRequest(_Model):
    reports: list[TriageRequest] = Field(min_length=1, max_length=50)


class AcknowledgeRequest(_Model):
    acknowledged_by: str = Field(max_length=200)
    note: str | None = Field(default=None, max_length=500)
