package main

import (
	"math"
	"time"
)

const iso8601 = time.RFC3339

// mapPublicStatus maps an internal reports-service status to the reduced public
// enum. CLOSED reports are excluded from public views entirely (included=false).
//
//	SUBMITTED   -> SUBMITTED
//	TRIAGED     -> SUBMITTED  (not yet actioned from the public's perspective)
//	IN_PROGRESS -> IN_PROGRESS
//	RESOLVED    -> RESOLVED
//	ESCALATED   -> ESCALATED
//	CLOSED      -> excluded
func mapPublicStatus(internal string) (public string, included bool) {
	switch internal {
	case "SUBMITTED", "TRIAGED":
		return "SUBMITTED", true
	case "IN_PROGRESS":
		return "IN_PROGRESS", true
	case "RESOLVED":
		return "RESOLVED", true
	case "ESCALATED":
		return "ESCALATED", true
	default: // CLOSED and anything unrecognized
		return "", false
	}
}

// estimatedResponseTime derives a human-readable ETA from severity and public
// status. Returns nil once resolved (nothing left to estimate).
func estimatedResponseTime(severity, publicStatus string) *string {
	if publicStatus == "RESOLVED" {
		return nil
	}
	if publicStatus == "ESCALATED" {
		return strptr("Immediate")
	}
	var eta string
	switch severity {
	case "CRITICAL":
		eta = "Immediate"
	case "HIGH":
		eta = "Within 24 hours"
	case "MEDIUM":
		eta = "1–2 business days"
	default: // LOW
		eta = "3–5 business days"
	}
	return strptr(eta)
}

func strptr(s string) *string { return &s }

// grid3 rounds a coordinate to 3 decimal places (~110m precision) for heatmap
// aggregation, per CLAUDE.md. Coarse by design — exact locations are not exposed.
func grid3(v float64) float64 {
	return math.Round(v*1000) / 1000
}

// windowStart converts a window token to an absolute cutoff. "all" returns the
// zero time (no lower bound). now is passed in for testability.
func windowStart(window string, now time.Time) time.Time {
	switch window {
	case "24h":
		return now.Add(-24 * time.Hour)
	case "7d":
		return now.AddDate(0, 0, -7)
	case "30d":
		return now.AddDate(0, 0, -30)
	case "90d":
		return now.AddDate(0, 0, -90)
	default: // "all"
		return time.Time{}
	}
}

// filterByWindow returns reports created at or after the window cutoff.
func filterByWindow(reports []Report, window string, now time.Time) []Report {
	start := windowStart(window, now)
	if start.IsZero() {
		return reports
	}
	out := make([]Report, 0, len(reports))
	for _, r := range reports {
		if !r.CreatedAt.Before(start) {
			out = append(out, r)
		}
	}
	return out
}
