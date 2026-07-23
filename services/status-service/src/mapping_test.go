package main

import (
	"testing"
	"time"
)

func TestMapPublicStatus(t *testing.T) {
	cases := []struct {
		in       string
		want     string
		included bool
	}{
		{"SUBMITTED", "SUBMITTED", true},
		{"TRIAGED", "SUBMITTED", true}, // triaged is not yet actioned from the public view
		{"IN_PROGRESS", "IN_PROGRESS", true},
		{"RESOLVED", "RESOLVED", true},
		{"ESCALATED", "ESCALATED", true},
		{"CLOSED", "", false},
		{"BOGUS", "", false},
	}
	for _, c := range cases {
		got, inc := mapPublicStatus(c.in)
		if got != c.want || inc != c.included {
			t.Errorf("mapPublicStatus(%q) = (%q,%v), want (%q,%v)", c.in, got, inc, c.want, c.included)
		}
	}
}

func TestEstimatedResponseTime(t *testing.T) {
	if estimatedResponseTime("LOW", "RESOLVED") != nil {
		t.Error("resolved reports should have no ETA")
	}
	if got := estimatedResponseTime("LOW", "ESCALATED"); got == nil || *got != "Immediate" {
		t.Errorf("escalated should be Immediate, got %v", got)
	}
	if got := estimatedResponseTime("CRITICAL", "SUBMITTED"); got == nil || *got != "Immediate" {
		t.Errorf("critical should be Immediate, got %v", got)
	}
	if got := estimatedResponseTime("LOW", "SUBMITTED"); got == nil || *got != "3–5 business days" {
		t.Errorf("low should be 3–5 business days, got %v", got)
	}
}

func TestGrid3(t *testing.T) {
	if got := grid3(44.78349); got != 44.783 {
		t.Errorf("grid3(44.78349) = %v, want 44.783", got)
	}
}

func TestFilterByWindow(t *testing.T) {
	now := time.Date(2026, 7, 23, 12, 0, 0, 0, time.UTC)
	reports := []Report{
		{ReportID: "recent", CreatedAt: now.Add(-1 * time.Hour)},
		{ReportID: "old", CreatedAt: now.AddDate(0, 0, -40)},
	}
	got := filterByWindow(reports, "30d", now)
	if len(got) != 1 || got[0].ReportID != "recent" {
		t.Errorf("30d window should keep only 'recent', got %+v", got)
	}
	if len(filterByWindow(reports, "all", now)) != 2 {
		t.Error("'all' window should keep everything")
	}
}
