"""Cross-service integration tests — exercise the real reports→triage→status flow
against live services + their real dependencies (Postgres/Redis/LocalStack).

These cover the seams that unit tests can't, and specifically guard the bugs found
during manual integration: the reports→triage payload contract, the severity
override + escalation, public status mapping, and the status cache.
"""
import flows


def test_all_services_healthy(client):
    for base in (flows.REPORTS_URL, flows.TRIAGE_URL, flows.STATUS_URL):
        r = client.get(f"{base}/health")
        assert r.status_code == 200, f"{base}/health -> {r.status_code}: {r.text}"
        assert r.json()["status"] in ("healthy", "degraded")


def test_pothole_full_lifecycle(client):
    """Submit → triage callback (TRIAGED) → assignment → acknowledge → IN_PROGRESS."""
    desc, lat, lng = flows.SAMPLE_INCIDENTS["POTHOLE"]
    rep = flows.create_report(client, "POTHOLE", desc, lat, lng)
    rid = rep["reportId"]
    assert rep["status"] == "SUBMITTED"

    # triage-service classifies and calls back — proves the reports→triage contract.
    flows.wait_for_report_status(client, rid, {"TRIAGED"})

    a = flows.get_assignment(client, rid)
    assert a.status_code == 200
    routing = a.json()["routing"]
    assert routing["assignedSeverity"] == "LOW"
    assert [d["department"] for d in routing["departments"]] == ["PUBLIC_WORKS"]

    assignment_id = a.json()["assignmentId"]
    ack = flows.acknowledge(client, "PUBLIC_WORKS", assignment_id)
    assert ack.status_code == 200
    assert ack.json()["status"] == "ACKNOWLEDGED"

    # acknowledge triggers the second callback → report becomes IN_PROGRESS.
    flows.wait_for_report_status(client, rid, {"IN_PROGRESS"})


def test_umbrella_severity_override_and_escalation(client):
    """Submitter says LOW; triage must override to CRITICAL, route to STARS_UNIT,
    flag immediate escalation, and drive the report to ESCALATED publicly."""
    desc, lat, lng = flows.SAMPLE_INCIDENTS["UMBRELLA_CORP_ACTIVITY"]
    rid = flows.create_report(client, "UMBRELLA_CORP_ACTIVITY", desc, lat, lng, severity="LOW")["reportId"]

    flows.wait_for_report_status(client, rid, {"ESCALATED"})
    routing = flows.get_assignment(client, rid).json()["routing"]
    assert routing["assignedSeverity"] == "CRITICAL"  # override, not the submitted LOW
    depts = routing["departments"]
    assert [d["department"] for d in depts] == ["STARS_UNIT"]
    assert depts[0]["immediateEscalation"] is True

    pub = flows.public_status(client, rid).json()
    assert pub["status"] == "ESCALATED"
    assert pub["estimatedResponseTime"] == "Immediate"


def test_zombie_dual_routing(client):
    desc, lat, lng = flows.SAMPLE_INCIDENTS["ZOMBIE_SIGHTING"]
    rid = flows.create_report(client, "ZOMBIE_SIGHTING", desc, lat, lng)["reportId"]
    flows.wait_for_report_status(client, rid, {"TRIAGED"})
    routing = flows.get_assignment(client, rid).json()["routing"]
    assert routing["assignedSeverity"] == "CRITICAL"
    assert [d["department"] for d in routing["departments"]] == ["RPD_EMERGENCY", "STARS_UNIT"]


def test_public_status_maps_triaged_to_submitted(client):
    """TRIAGED is an internal status; publicly it must read SUBMITTED."""
    desc, lat, lng = flows.SAMPLE_INCIDENTS["NOISE_COMPLAINT"]
    rid = flows.create_report(client, "NOISE_COMPLAINT", desc, lat, lng)["reportId"]
    flows.wait_for_report_status(client, rid, {"TRIAGED"})
    pub = flows.public_status(client, rid).json()
    assert pub["status"] == "SUBMITTED"  # not "TRIAGED"


def test_status_cache_hit_then_miss_headers(client):
    desc, lat, lng = flows.SAMPLE_INCIDENTS["POTHOLE"]
    rid = flows.create_report(client, "POTHOLE", desc, lat, lng)["reportId"]
    first = flows.public_status(client, rid)
    assert first.status_code == 200
    assert first.headers["X-Cache"] == "MISS"
    second = flows.public_status(client, rid)
    assert second.headers["X-Cache"] == "HIT"


def test_triage_is_internal_only(client):
    """triage-service rejects unauthenticated calls (it has no public ingress)."""
    desc, lat, lng = flows.SAMPLE_INCIDENTS["POTHOLE"]
    rid = flows.create_report(client, "POTHOLE", desc, lat, lng)["reportId"]
    assert flows.get_assignment(client, rid, token=False).status_code == 401


def test_attachment_upload_and_type_rejection(client):
    desc, lat, lng = flows.SAMPLE_INCIDENTS["VANDALISM"]
    rid = flows.create_report(client, "VANDALISM", desc, lat, lng)["reportId"]

    up = flows.upload_attachment(client, rid)
    assert up.status_code == 201
    body = up.json()
    assert body["mimeType"] == "image/png"
    assert body["url"].startswith("http")  # pre-signed S3 URL

    listing = client.get(f"{flows.REPORTS_URL}/reports/{rid}/attachments").json()
    assert len(listing["attachments"]) == 1

    bad = flows.upload_attachment(client, rid, filename="notes.txt", content=b"nope", mime="text/plain")
    assert bad.status_code == 415


def test_feed_and_stats_reflect_activity(client):
    """Create one of each type, then confirm the public aggregates are populated
    and correctly shaped. Note: /feed and /stats are cached (60s / 5min) and are
    NOT invalidated on write, so we assert on populated/mapped state rather than an
    exact post-write delta (which would race the cache TTL)."""
    for t, (desc, lat, lng) in flows.SAMPLE_INCIDENTS.items():
        flows.create_report(client, t, desc, lat, lng)

    feed = flows.feed(client, limit=100).json()
    assert feed["total"] >= 8  # at least the eight distinct types we just submitted
    for item in feed["incidents"]:
        # Public feed never exposes internal TRIAGED or CLOSED.
        assert item["status"] in ("SUBMITTED", "IN_PROGRESS", "RESOLVED", "ESCALATED")

    totals = flows.stats(client, "all").json()["totals"]
    assert sum(totals.values()) >= 8

    assert "points" in flows.heatmap(client).json()
