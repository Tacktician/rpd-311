package main

import "time"

// --- Enum value sets (must match the OpenAPI specs across all three services) ---

var incidentTypes = map[string]bool{
	"POTHOLE": true, "DOWNED_TREE": true, "NOISE_COMPLAINT": true, "SUSPICIOUS_PERSON": true,
	"VANDALISM": true, "CAR_BREAK_IN": true, "ZOMBIE_SIGHTING": true, "UMBRELLA_CORP_ACTIVITY": true,
}

var severityLevels = map[string]bool{"LOW": true, "MEDIUM": true, "HIGH": true, "CRITICAL": true}

var publicStatuses = map[string]bool{
	"SUBMITTED": true, "IN_PROGRESS": true, "RESOLVED": true, "ESCALATED": true,
}

var severityRank = map[string]int{"LOW": 1, "MEDIUM": 2, "HIGH": 3, "CRITICAL": 4}

// --- Upstream shapes (as returned by reports-service) ---

type Location struct {
	Lat     float64 `json:"lat"`
	Lng     float64 `json:"lng"`
	Address string  `json:"address,omitempty"`
}

// Report mirrors reports-service ReportResponse. Only fields this service needs
// are consumed; sensitive fields are not present in that response by design.
type Report struct {
	ReportID  string    `json:"reportId"`
	Type      string    `json:"type"`
	Location  Location  `json:"location"`
	Severity  string    `json:"severity"`
	Status    string    `json:"status"`
	Anonymous bool      `json:"anonymous"`
	CreatedAt time.Time `json:"createdAt"`
	UpdatedAt time.Time `json:"updatedAt"`
}

type ReportList struct {
	Reports []Report `json:"reports"`
	Total   int      `json:"total"`
	Limit   int      `json:"limit"`
	Offset  int      `json:"offset"`
}

// --- Public response shapes (defined in status-service openapi.yaml) ---

type PublicStatusResponse struct {
	ReportID              string   `json:"reportId"`
	Type                  string   `json:"type"`
	Status                string   `json:"status"`
	Severity              string   `json:"severity"`
	Location              Location `json:"location"`
	SubmittedAt           string   `json:"submittedAt"`
	UpdatedAt             string   `json:"updatedAt"`
	EstimatedResponseTime *string  `json:"estimatedResponseTime"`
	PublicNote            *string  `json:"publicNote"`
}

type FeedItem struct {
	ReportID    string   `json:"reportId"`
	Type        string   `json:"type"`
	Status      string   `json:"status"`
	Severity    string   `json:"severity"`
	Location    Location `json:"location"`
	SubmittedAt string   `json:"submittedAt"`
	PublicNote  *string  `json:"publicNote"`
}

type FeedResponse struct {
	Incidents []FeedItem `json:"incidents"`
	Total     int        `json:"total"`
	Limit     int        `json:"limit"`
	Offset    int        `json:"offset"`
	OldestAt  *string    `json:"oldestAt"`
	NewestAt  *string    `json:"newestAt"`
}

type StatsTotals struct {
	Submitted  int `json:"submitted"`
	Triaged    int `json:"triaged"`
	InProgress int `json:"inProgress"`
	Resolved   int `json:"resolved"`
	Escalated  int `json:"escalated"`
}

type StatsResponse struct {
	Window                 string             `json:"window"`
	GeneratedAt            string             `json:"generatedAt"`
	Totals                 StatsTotals        `json:"totals"`
	ByType                 map[string]int     `json:"byType"`
	BySeverity             map[string]int     `json:"bySeverity"`
	AverageResolutionHours map[string]float64 `json:"averageResolutionHours"`
}

type StatsByType struct {
	Type                   string         `json:"type"`
	Total                  int            `json:"total"`
	Resolved               int            `json:"resolved"`
	ResolutionRatePct      float64        `json:"resolutionRatePct"`
	AverageResolutionHours float64        `json:"averageResolutionHours"`
	BySeverity             map[string]int `json:"bySeverity"`
}

type StatsByTypeResponse struct {
	Window      string        `json:"window"`
	GeneratedAt string        `json:"generatedAt"`
	Types       []StatsByType `json:"types"`
}

type HeatmapPoint struct {
	Lat              float64 `json:"lat"`
	Lng              float64 `json:"lng"`
	Weight           int     `json:"weight"`
	DominantType     string  `json:"dominantType,omitempty"`
	DominantSeverity string  `json:"dominantSeverity,omitempty"`
}

type HeatmapResponse struct {
	Window      string         `json:"window"`
	GeneratedAt string         `json:"generatedAt"`
	Points      []HeatmapPoint `json:"points"`
}

type HealthResponse struct {
	Status       string            `json:"status"`
	Service      string            `json:"service"`
	Version      string            `json:"version"`
	Timestamp    string            `json:"timestamp"`
	Dependencies map[string]string `json:"dependencies"`
}
