package main

import (
	"crypto/rand"
	"encoding/json"
	"fmt"
	"net/http"
	"strconv"
)

func itoa(n int) string     { return strconv.Itoa(n) }
func ftoa(f float64) string { return strconv.FormatFloat(f, 'f', -1, 64) }

type ctxKey string

const (
	ctxRequestID ctxKey = "requestID"
	ctxTrace     ctxKey = "trace"
)

func requestIDFrom(r *http.Request) string {
	if v, ok := r.Context().Value(ctxRequestID).(string); ok {
		return v
	}
	return ""
}

func traceHeadersFrom(r *http.Request) map[string]string {
	if v, ok := r.Context().Value(ctxTrace).(map[string]string); ok {
		return v
	}
	return map[string]string{}
}

// uuidV4 generates a random UUID v4 string without an external dependency.
func uuidV4() string {
	var b [16]byte
	_, _ = rand.Read(b[:])
	b[6] = (b[6] & 0x0f) | 0x40 // version 4
	b[8] = (b[8] & 0x3f) | 0x80 // variant 10
	return fmt.Sprintf("%x-%x-%x-%x-%x", b[0:4], b[4:6], b[6:8], b[8:10], b[10:16])
}

// apiError is a typed HTTP error serialized into the shared RPD 311 error shape.
type apiError struct {
	Status  int
	Code    string
	Message string
}

func (e apiError) Error() string { return e.Message }

func aptr(e apiError) *apiError { return &e }

var errNotFound = func(msg string) apiError { return apiError{http.StatusNotFound, "NOT_FOUND", msg} }
var errBadRequest = func(msg string) apiError { return apiError{http.StatusBadRequest, "VALIDATION_ERROR", msg} }
var errUnauthorized = func(msg string) apiError { return apiError{http.StatusUnauthorized, "UNAUTHORIZED", msg} }
var errUpstream = func(msg string) apiError { return apiError{http.StatusServiceUnavailable, "UPSTREAM_UNAVAILABLE", msg} }

func writeJSON(w http.ResponseWriter, status int, v any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(v)
}

func writeError(w http.ResponseWriter, r *http.Request, e apiError) {
	writeJSON(w, e.Status, map[string]any{
		"error":     e.Code,
		"message":   e.Message,
		"requestId": requestIDFrom(r),
	})
}
