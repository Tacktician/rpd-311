"""Unit tests for request-model validation (camelCase aliasing, bounds, strictness)."""
import pytest
from pydantic import ValidationError

from src.schemas import AcknowledgeRequest, TriageRequest


VALID = {
    "reportId": "a3f1c2d4-7e8b-4a9f-b0c1-2d3e4f5a6b7c",
    "type": "ZOMBIE_SIGHTING",
    "description": "Multiple individuals moving erratically on Main Street.",
    "location": {"lat": 44.7891, "lng": -93.2251, "address": "Main Street"},
    "submitterSeverity": "CRITICAL",
    "receivedAt": "2026-07-22T03:01:00Z",
}


def test_parses_camelcase_payload():
    req = TriageRequest.model_validate(VALID)
    assert req.type.value == "ZOMBIE_SIGHTING"
    assert str(req.report_id) == "a3f1c2d4-7e8b-4a9f-b0c1-2d3e4f5a6b7c"
    assert req.location.lat == pytest.approx(44.7891)


def test_submitter_severity_is_optional():
    payload = {k: v for k, v in VALID.items() if k != "submitterSeverity"}
    req = TriageRequest.model_validate(payload)
    assert req.submitter_severity is None


def test_rejects_unknown_incident_type():
    with pytest.raises(ValidationError):
        TriageRequest.model_validate({**VALID, "type": "GOLEM_SIGHTING"})


def test_rejects_out_of_range_latitude():
    with pytest.raises(ValidationError):
        TriageRequest.model_validate({**VALID, "location": {"lat": 200, "lng": 0}})


def test_rejects_unknown_field_strict():
    with pytest.raises(ValidationError):
        TriageRequest.model_validate({**VALID, "hax": True})


def test_missing_required_field():
    with pytest.raises(ValidationError):
        TriageRequest.model_validate({k: v for k, v in VALID.items() if k != "receivedAt"})


def test_acknowledge_requires_acknowledged_by():
    with pytest.raises(ValidationError):
        AcknowledgeRequest.model_validate({"note": "no id given"})
    ok = AcknowledgeRequest.model_validate({"acknowledgedBy": "RPD-DISPATCH-001"})
    assert ok.acknowledged_by == "RPD-DISPATCH-001"
