package main

import "testing"

func TestDeriveOutboundTraceparent(t *testing.T) {
	// Originates when absent.
	out := deriveOutboundTraceparent("")
	if !traceparentRe.MatchString(out) {
		t.Fatalf("originated traceparent is malformed: %q", out)
	}
	if out[len(out)-3:] != "-01" {
		t.Errorf("expected sampled flags -01, got %q", out)
	}

	// Continues an inbound trace with a fresh span-id.
	inbound := "00-0af7651916cd43dd8448eb211c80319c-b7ad6b7169203331-01"
	m := traceparentRe.FindStringSubmatch(deriveOutboundTraceparent(inbound))
	if m == nil {
		t.Fatal("continued traceparent is malformed")
	}
	if m[1] != "0af7651916cd43dd8448eb211c80319c" {
		t.Errorf("trace-id not preserved: %q", m[1])
	}
	if m[2] == "b7ad6b7169203331" {
		t.Errorf("span-id should be fresh, got the inbound one: %q", m[2])
	}

	// Originates on malformed input.
	if !traceparentRe.MatchString(deriveOutboundTraceparent("garbage")) {
		t.Error("malformed inbound should yield a fresh valid traceparent")
	}

	// Unique span per call.
	if deriveOutboundTraceparent("") == deriveOutboundTraceparent("") {
		t.Error("expected a unique span-id per call")
	}
}
