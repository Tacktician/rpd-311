"""Unit tests for W3C traceparent derivation."""
import re

from src.tracing_util import derive_outbound_traceparent

RE = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$")


def test_originates_when_absent():
    tp = derive_outbound_traceparent(None)
    assert RE.match(tp)
    assert tp.endswith("-01")


def test_continues_trace_with_fresh_span():
    inbound = "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
    m = RE.match(derive_outbound_traceparent(inbound))
    assert m.group(1) == "0af7651916cd43dd8448eb211c80319c"  # trace-id preserved
    assert m.group(2) != "b7ad6b7169203331"  # new span for this hop


def test_originates_on_malformed_input():
    out = derive_outbound_traceparent("not-a-traceparent")
    assert RE.match(out)
    assert "not-a-traceparent" not in out


def test_span_id_unique_per_call():
    assert derive_outbound_traceparent(None) != derive_outbound_traceparent(None)
