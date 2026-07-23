package main

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"net/http"
	"regexp"
)

var traceparentRe = regexp.MustCompile(`^00-([0-9a-f]{32})-([0-9a-f]{16})-([0-9a-f]{2})$`)

func randHex(n int) string {
	b := make([]byte, n)
	_, _ = rand.Read(b)
	return hex.EncodeToString(b)
}

// deriveOutboundTraceparent continues an inbound trace (reusing its trace-id with
// a fresh span-id for this service's work) or originates a new one when the inbound
// header is absent/malformed. Originating at the public entry point is what lets the
// Postman API Catalog Service Graph link this service to its downstream calls.
func deriveOutboundTraceparent(inbound string) string {
	traceID := randHex(16) // 16 bytes -> 32 hex
	flags := "01"          // default: sampled
	if m := traceparentRe.FindStringSubmatch(inbound); m != nil {
		traceID, flags = m[1], m[3]
	}
	return "00-" + traceID + "-" + randHex(8) + "-" + flags
}

// requestIDMiddleware assigns a UUID v4 to each request, echoes it on the
// response, and exposes it via context for the error shape.
func requestIDMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		id := uuidV4()
		w.Header().Set("X-Request-Id", id)
		ctx := context.WithValue(r.Context(), ctxRequestID, id)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// tracingMiddleware reads W3C trace headers and stashes them in context so every
// outbound call can forward them. This populates the Service Graph in Postman
// API Catalog — without it, edges between services do not appear.
func (a *App) tracingMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		trace := map[string]string{}
		if a.cfg.TraceEnabled {
			trace["traceparent"] = deriveOutboundTraceparent(r.Header.Get("traceparent"))
			if ts := r.Header.Get("tracestate"); ts != "" {
				trace["tracestate"] = ts
			}
		}
		ctx := context.WithValue(r.Context(), ctxTrace, trace)
		next.ServeHTTP(w, r.WithContext(ctx))
	})
}

// serviceTokenMiddleware guards internal-only endpoints (cache invalidation).
func (a *App) serviceTokenMiddleware(next http.Handler) http.Handler {
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if token := r.Header.Get("X-Service-Token"); token == "" || token != a.cfg.ServiceToken {
			writeError(w, r, errUnauthorized("Service token missing or invalid. This endpoint is internal only."))
			return
		}
		next.ServeHTTP(w, r)
	})
}
