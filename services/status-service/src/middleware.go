package main

import (
	"context"
	"net/http"
)

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
			if tp := r.Header.Get("traceparent"); tp != "" {
				trace["traceparent"] = tp
				if ts := r.Header.Get("tracestate"); ts != "" {
					trace["tracestate"] = ts
				}
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
