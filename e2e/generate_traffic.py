#!/usr/bin/env python3
"""RPD 311 demo traffic generator.

Drives the full reports→triage→status call graph on a loop so the Postman Insights
Agent has rich, connected traffic to build the Service Graph from — including edges
into the internal triage-service. Reuses the same flows as the integration tests.

Requests are sent WITHOUT a traceparent (the realistic resident case), so the
services originate one — exactly the path the Service Graph depends on.

Usage:
  python generate_traffic.py                 # run forever, ~2s between reports
  python generate_traffic.py -n 50 -d 0.5    # 50 reports, 0.5s apart
  REPORTS_URL=... TRIAGE_URL=... STATUS_URL=... python generate_traffic.py
"""
from __future__ import annotations

import argparse
import itertools
import random
import sys
import time

import httpx

import flows


def jitter(lat, lng):
    # Spread points ~a few hundred meters so the heatmap has texture.
    return round(lat + random.uniform(-0.004, 0.004), 6), round(lng + random.uniform(-0.004, 0.004), 6)


def one_cycle(c) -> str:
    incident_type = random.choice(list(flows.SAMPLE_INCIDENTS))
    desc, lat, lng = flows.SAMPLE_INCIDENTS[incident_type]
    lat, lng = jitter(lat, lng)

    rid = flows.create_report(c, incident_type, desc, lat, lng)["reportId"]

    # Let triage classify (fire-and-forget callback), then read the public views —
    # this exercises status → reports/triage as well.
    try:
        flows.wait_for_report_status(c, rid, {"TRIAGED", "ESCALATED"}, timeout=5.0)
    except AssertionError:
        pass  # triage may lag under load; keep the traffic flowing

    flows.public_status(c, rid)

    # Occasionally acknowledge a queued assignment to drive the IN_PROGRESS path.
    if random.random() < 0.4:
        a = flows.get_assignment(c, rid)
        if a.status_code == 200 and a.json()["status"] == "PENDING":
            dept = a.json()["routing"]["departments"][0]["department"]
            flows.acknowledge(c, dept, a.json()["assignmentId"], by="RPD-DISPATCH-DEMO")

    # Occasionally attach a photo (reports → S3).
    if random.random() < 0.3:
        flows.upload_attachment(c, rid)

    # Public reads that hit status-service aggregates.
    flows.feed(c, limit=10)
    flows.stats(c, window="24h")
    return f"{incident_type} -> {rid[:8]}"


def main():
    ap = argparse.ArgumentParser(description="RPD 311 demo traffic generator")
    ap.add_argument("-n", "--iterations", type=int, default=0, help="number of reports (0 = forever)")
    ap.add_argument("-d", "--delay", type=float, default=2.0, help="seconds between reports")
    args = ap.parse_args()

    flows.wait_for_health(timeout=60)
    print(f"RPD 311 traffic generator online. reports={flows.REPORTS_URL} status={flows.STATUS_URL}")

    counter = itertools.count(1)
    sent = 0
    try:
        with httpx.Client(timeout=10.0) as c:
            while args.iterations == 0 or sent < args.iterations:
                i = next(counter)
                try:
                    print(f"[{i}] {one_cycle(c)}")
                    sent += 1
                except httpx.HTTPError as exc:
                    print(f"[{i}] transient error: {exc}", file=sys.stderr)
                time.sleep(args.delay)
    except KeyboardInterrupt:
        print(f"\nstopped after {sent} reports.")


if __name__ == "__main__":
    main()
