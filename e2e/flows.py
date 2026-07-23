"""Shared RPD 311 cross-service flows.

Used by BOTH the integration tests (test_flow.py) and the demo traffic generator
(generate_traffic.py). Everything talks to the services over HTTP exactly as a real
client would — the same calls that populate the Postman API Catalog Service Graph.

Service URLs and the internal token come from the environment (defaults match
docker-compose.local.yml), so this runs unchanged locally and in CI.
"""
from __future__ import annotations

import base64
import os
import time

import httpx

REPORTS_URL = os.environ.get("REPORTS_URL", "http://localhost:3001/v1")
TRIAGE_URL = os.environ.get("TRIAGE_URL", "http://localhost:3002/v1")
STATUS_URL = os.environ.get("STATUS_URL", "http://localhost:3003/v1")
SERVICE_TOKEN = os.environ.get("SERVICE_TOKEN", "changeme-service-token")

TOKEN_HEADER = {"X-Service-Token": SERVICE_TOKEN}

# Expected triage classification per type: (severity, [departments], immediate_escalation).
# Mirrors the routing table in triage-service — the assertions' source of truth.
ROUTING = {
    "POTHOLE": ("LOW", ["PUBLIC_WORKS"], False),
    "DOWNED_TREE": ("LOW", ["PUBLIC_WORKS"], False),
    "NOISE_COMPLAINT": ("MEDIUM", ["RPD_NON_EMERGENCY"], False),
    "SUSPICIOUS_PERSON": ("MEDIUM", ["RPD_NON_EMERGENCY"], False),
    "VANDALISM": ("MEDIUM", ["RPD_NON_EMERGENCY", "SANITATION"], False),
    "CAR_BREAK_IN": ("HIGH", ["RPD_EMERGENCY"], False),
    "ZOMBIE_SIGHTING": ("CRITICAL", ["RPD_EMERGENCY", "STARS_UNIT"], False),
    "UMBRELLA_CORP_ACTIVITY": ("CRITICAL", ["STARS_UNIT"], True),
}

# Deadpan Raccoon City sample incidents for the traffic generator, one per type.
SAMPLE_INCIDENTS = {
    "POTHOLE": ("Crater-sized pothole swallowing bicycle tires on 5th Ave.", 44.7744, -93.2133),
    "DOWNED_TREE": ("Oak down across Weskerway after the storm; road impassable.", 44.7760, -93.2150),
    "NOISE_COMPLAINT": ("Sustained groaning from apartment 4B since roughly 2am.", 44.7831, -93.2185),
    "SUSPICIOUS_PERSON": ("Individual in a lab coat photographing the water treatment plant.", 44.7702, -93.2110),
    "VANDALISM": ("Spray paint across the transit shelter on Oak Street.", 44.7801, -93.2201),
    "CAR_BREAK_IN": ("Sedan window smashed near the precinct lot; glass everywhere.", 44.7810, -93.2210),
    "ZOMBIE_SIGHTING": ("Several individuals moving erratically near the clock tower; unresponsive.", 44.7891, -93.2251),
    "UMBRELLA_CORP_ACTIVITY": ("Unmarked vans unloading biohazard containers at the Annex at 0300hrs.", 44.7712, -93.2099),
}

# 1x1 transparent PNG for attachment tests/traffic.
PIXEL_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAAC0lEQVR4nGNgYGAAAAAEAAH2FzhVAAAAAElFTkSuQmCC"
)


def wait_for_health(timeout: float = 60.0) -> None:
    """Block until all three services report a servable /health, or raise."""
    deadline = time.time() + timeout
    targets = {"reports": REPORTS_URL, "triage": TRIAGE_URL, "status": STATUS_URL}
    last = {}
    with httpx.Client(timeout=5.0) as c:
        while time.time() < deadline:
            ok = True
            for name, base in targets.items():
                try:
                    # 200 healthy/degraded or 503 unhealthy both mean "serving"; connection error means not up.
                    r = c.get(f"{base}/health")
                    last[name] = r.status_code
                    if r.status_code >= 500:
                        ok = False
                except httpx.HTTPError as exc:
                    last[name] = str(exc)
                    ok = False
            if ok:
                return
            time.sleep(2)
    raise RuntimeError(f"services not healthy within {timeout}s: {last}")


def create_report(c, incident_type, description, lat, lng, address=None, severity=None, traceparent=None):
    body = {"type": incident_type, "description": description, "location": {"lat": lat, "lng": lng}}
    if address:
        body["location"]["address"] = address
    if severity:
        body["severity"] = severity
    headers = {"traceparent": traceparent} if traceparent else {}
    r = c.post(f"{REPORTS_URL}/reports", json=body, headers=headers)
    r.raise_for_status()
    return r.json()


def get_report(c, report_id):
    return c.get(f"{REPORTS_URL}/reports/{report_id}")


def wait_for_report_status(c, report_id, expected: set[str], timeout: float = 10.0):
    """Poll the report until its status is in `expected` (triage callback is async)."""
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        r = get_report(c, report_id)
        if r.status_code == 200:
            last = r.json()["status"]
            if last in expected:
                return last
        time.sleep(0.5)
    raise AssertionError(f"report {report_id} status {last!r} never reached {expected}")


def get_assignment(c, report_id, token=True):
    headers = TOKEN_HEADER if token else {}
    return c.get(f"{TRIAGE_URL}/assignments/{report_id}", headers=headers)


def acknowledge(c, department, assignment_id, by="INTEGRATION-HARNESS"):
    return c.post(
        f"{TRIAGE_URL}/queue/{department}/assignments/{assignment_id}/acknowledge",
        headers=TOKEN_HEADER,
        json={"acknowledgedBy": by, "note": "Acknowledged by the integration harness."},
    )


def public_status(c, report_id):
    return c.get(f"{STATUS_URL}/status/{report_id}")


def feed(c, **params):
    return c.get(f"{STATUS_URL}/feed", params=params)


def stats(c, window="all"):
    return c.get(f"{STATUS_URL}/stats", params={"window": window})


def heatmap(c, window="7d"):
    return c.get(f"{STATUS_URL}/stats/heatmap", params={"window": window})


def upload_attachment(c, report_id, filename="evidence.png", content=PIXEL_PNG, mime="image/png"):
    files = {"file": (filename, content, mime)}
    return c.post(f"{REPORTS_URL}/reports/{report_id}/attachments", files=files, data={"caption": "Scene photo."})
