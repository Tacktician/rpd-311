"""W3C traceparent derivation (stdlib only, no framework imports so it's unit-testable).

Continue an inbound trace (reuse its trace-id, emit a fresh span-id for this
service's work) or originate a new trace when there is no valid inbound header.
See reports-service tracing.js for the rationale.
"""
from __future__ import annotations

import re
import secrets

_TRACEPARENT_RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


def derive_outbound_traceparent(inbound: str | None) -> str:
    trace_id = secrets.token_hex(16)  # 16 bytes -> 32 hex
    flags = "01"  # default: sampled
    if inbound:
        match = _TRACEPARENT_RE.match(inbound)
        if match:
            trace_id, flags = match.group(1), match.group(3)
    span_id = secrets.token_hex(8)  # 8 bytes -> 16 hex, this service's span
    return f"00-{trace_id}-{span_id}-{flags}"
