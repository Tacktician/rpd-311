"""Unit tests for the triage classification engine — the routing table is the
load-bearing business logic for this service."""
from src.routing import ROUTING_TABLE, batch_priority_key, classify


def test_every_incident_type_is_routable():
    expected = {
        "POTHOLE", "DOWNED_TREE", "NOISE_COMPLAINT", "SUSPICIOUS_PERSON",
        "VANDALISM", "CAR_BREAK_IN", "ZOMBIE_SIGHTING", "UMBRELLA_CORP_ACTIVITY",
    }
    assert set(ROUTING_TABLE) == expected


def test_pothole_is_low_public_works():
    d = classify("POTHOLE")
    assert d["assignedSeverity"] == "LOW"
    assert [x["department"] for x in d["departments"]] == ["PUBLIC_WORKS"]
    assert d["departments"][0]["isPrimary"] is True
    assert d["immediateEscalation"] is False


def test_vandalism_routes_to_two_departments_with_one_primary():
    d = classify("VANDALISM")
    assert d["assignedSeverity"] == "MEDIUM"
    depts = d["departments"]
    assert [x["department"] for x in depts] == ["RPD_NON_EMERGENCY", "SANITATION"]
    assert depts[0]["isPrimary"] is True
    assert depts[1]["isPrimary"] is False


def test_zombie_sighting_is_critical_dual_routed_no_escalation():
    d = classify("ZOMBIE_SIGHTING")
    assert d["assignedSeverity"] == "CRITICAL"
    assert [x["department"] for x in d["departments"]] == ["RPD_EMERGENCY", "STARS_UNIT"]
    assert d["immediateEscalation"] is False


def test_umbrella_activity_is_critical_immediate_stars():
    d = classify("UMBRELLA_CORP_ACTIVITY")
    assert d["assignedSeverity"] == "CRITICAL"
    assert [x["department"] for x in d["departments"]] == ["STARS_UNIT"]
    assert d["immediateEscalation"] is True
    assert d["departments"][0]["immediateEscalation"] is True
    assert "Immediate escalation" in d["classificationReason"]


def test_batch_priority_puts_escalation_types_first():
    body_order = ["POTHOLE", "NOISE_COMPLAINT", "UMBRELLA_CORP_ACTIVITY", "CAR_BREAK_IN", "ZOMBIE_SIGHTING"]
    ordered = sorted(body_order, key=batch_priority_key)
    # The two escalation types come first (in some order), everything else after.
    assert set(ordered[:2]) == {"UMBRELLA_CORP_ACTIVITY", "ZOMBIE_SIGHTING"}
    assert ordered[2:] == ["CAR_BREAK_IN", "NOISE_COMPLAINT", "POTHOLE"]
