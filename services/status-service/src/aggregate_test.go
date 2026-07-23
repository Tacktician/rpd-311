package main

import (
	"testing"
	"time"
)

var testNow = time.Date(2026, 7, 23, 12, 0, 0, 0, time.UTC)

func ts(s string) time.Time {
	t, err := time.Parse(time.RFC3339, s)
	if err != nil {
		panic(err)
	}
	return t
}

// A fixed sample used across aggregation tests. r5 is CLOSED (must be excluded);
// r2 and r3 fall in the same ~100m heatmap cell.
func sampleReports() []Report {
	return []Report{
		{ReportID: "r1", Type: "POTHOLE", Severity: "LOW", Status: "RESOLVED",
			Location: Location{Lat: 44.7744, Lng: -93.2133}, CreatedAt: ts("2026-07-20T09:00:00Z"), UpdatedAt: ts("2026-07-22T09:00:00Z")},
		{ReportID: "r2", Type: "NOISE_COMPLAINT", Severity: "MEDIUM", Status: "SUBMITTED",
			Location: Location{Lat: 44.7831, Lng: -93.2185}, CreatedAt: ts("2026-07-23T02:00:00Z"), UpdatedAt: ts("2026-07-23T02:00:00Z")},
		{ReportID: "r3", Type: "ZOMBIE_SIGHTING", Severity: "CRITICAL", Status: "ESCALATED",
			Location: Location{Lat: 44.7834, Lng: -93.2189}, CreatedAt: ts("2026-07-23T03:00:00Z"), UpdatedAt: ts("2026-07-23T03:00:00Z")},
		{ReportID: "r4", Type: "CAR_BREAK_IN", Severity: "HIGH", Status: "TRIAGED",
			Location: Location{Lat: 44.8000, Lng: -93.3000}, CreatedAt: ts("2026-07-23T04:00:00Z"), UpdatedAt: ts("2026-07-23T04:00:00Z")},
		{ReportID: "r5", Type: "VANDALISM", Severity: "MEDIUM", Status: "CLOSED",
			Location: Location{Lat: 44.7000, Lng: -93.2000}, CreatedAt: ts("2026-07-23T05:00:00Z"), UpdatedAt: ts("2026-07-23T05:00:00Z")},
	}
}

func TestBuildFeedExcludesClosedAndSortsNewestFirst(t *testing.T) {
	resp := buildFeed(sampleReports(), feedFilter{limit: 20, offset: 0})
	if resp.Total != 4 {
		t.Fatalf("expected 4 non-CLOSED incidents, got %d", resp.Total)
	}
	if resp.Incidents[0].ReportID != "r4" {
		t.Errorf("expected newest (r4) first, got %s", resp.Incidents[0].ReportID)
	}
	for _, it := range resp.Incidents {
		if it.ReportID == "r5" {
			t.Error("CLOSED report r5 must not appear in the feed")
		}
	}
}

func TestBuildFeedStatusFilterMapsTriaged(t *testing.T) {
	// status=SUBMITTED must include the TRIAGED report (r4), which maps to SUBMITTED.
	resp := buildFeed(sampleReports(), feedFilter{status: "SUBMITTED", limit: 20})
	ids := map[string]bool{}
	for _, it := range resp.Incidents {
		ids[it.ReportID] = true
		if it.Status != "SUBMITTED" {
			t.Errorf("filtered feed contained status %s", it.Status)
		}
	}
	if !ids["r2"] || !ids["r4"] {
		t.Errorf("expected r2 and r4 in SUBMITTED feed, got %v", ids)
	}
}

func TestBuildFeedPagination(t *testing.T) {
	resp := buildFeed(sampleReports(), feedFilter{limit: 2, offset: 1})
	if resp.Total != 4 || len(resp.Incidents) != 2 {
		t.Fatalf("expected total 4 with 2 on the page, got total=%d len=%d", resp.Total, len(resp.Incidents))
	}
	// offset 1 skips r4; page should start at r3.
	if resp.Incidents[0].ReportID != "r3" {
		t.Errorf("expected r3 first on page 2, got %s", resp.Incidents[0].ReportID)
	}
}

func TestBuildStats(t *testing.T) {
	s := buildStats(sampleReports(), "all", testNow)
	if s.Totals.Submitted != 1 || s.Totals.Triaged != 1 || s.Totals.Resolved != 1 || s.Totals.Escalated != 1 {
		t.Errorf("unexpected totals: %+v", s.Totals)
	}
	if s.ByType["POTHOLE"] != 1 || s.ByType["ZOMBIE_SIGHTING"] != 1 {
		t.Errorf("unexpected byType: %+v", s.ByType)
	}
	if _, ok := s.ByType["VANDALISM"]; ok {
		t.Error("CLOSED VANDALISM report must not appear in byType")
	}
	if s.AverageResolutionHours["LOW"] != 48.0 { // r1: 48h to resolve
		t.Errorf("expected LOW avg resolution 48.0, got %v", s.AverageResolutionHours["LOW"])
	}
}

func TestBuildHeatmapGroupsCellAndPicksDominantSeverity(t *testing.T) {
	h := buildHeatmap(sampleReports(), "30d", testNow)
	var cell *HeatmapPoint
	for i := range h.Points {
		if h.Points[i].Weight == 2 {
			cell = &h.Points[i]
		}
	}
	if cell == nil {
		t.Fatalf("expected one cell with weight 2 (r2+r3), got points %+v", h.Points)
	}
	if cell.DominantSeverity != "CRITICAL" {
		t.Errorf("expected dominant severity CRITICAL in the r2+r3 cell, got %s", cell.DominantSeverity)
	}
	// CLOSED r5 must not create a cell.
	for _, p := range h.Points {
		if p.Lat == grid3(44.7000) {
			t.Error("CLOSED report r5 must not appear in the heatmap")
		}
	}
}
