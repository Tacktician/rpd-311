package main

import (
	"fmt"
	"math"
	"sort"
	"time"
)

// Pure aggregation over a slice of reports. Handlers fetch the reports (from
// reports-service, window-filtered) and hand them here; keeping these functions
// pure makes the business logic straightforward to unit test.

type feedFilter struct {
	incidentType string // optional
	severity     string // optional
	status       string // optional public status
	since        time.Time
	limit        int
	offset       int
}

func round1(v float64) float64 { return math.Round(v*10) / 10 }

// buildFeed maps, filters, sorts (newest first), and paginates reports into the
// public feed. CLOSED reports are excluded via mapPublicStatus.
func buildFeed(reports []Report, f feedFilter) FeedResponse {
	items := make([]FeedItem, 0, len(reports))
	for _, r := range reports {
		public, ok := mapPublicStatus(r.Status)
		if !ok {
			continue
		}
		if f.incidentType != "" && r.Type != f.incidentType {
			continue
		}
		if f.severity != "" && r.Severity != f.severity {
			continue
		}
		if f.status != "" && public != f.status {
			continue
		}
		if !f.since.IsZero() && !r.CreatedAt.After(f.since) {
			continue
		}
		items = append(items, FeedItem{
			ReportID:    r.ReportID,
			Type:        r.Type,
			Status:      public,
			Severity:    r.Severity,
			Location:    r.Location,
			SubmittedAt: r.CreatedAt.UTC().Format(iso8601),
			PublicNote:  nil,
		})
	}

	// Newest first.
	sort.SliceStable(items, func(i, j int) bool {
		return items[i].SubmittedAt > items[j].SubmittedAt
	})

	total := len(items)
	start := f.offset
	if start > total {
		start = total
	}
	end := start + f.limit
	if end > total {
		end = total
	}
	page := items[start:end]

	resp := FeedResponse{Incidents: page, Total: total, Limit: f.limit, Offset: f.offset}
	if len(page) > 0 {
		newest := page[0].SubmittedAt
		oldest := page[len(page)-1].SubmittedAt
		resp.NewestAt = &newest
		resp.OldestAt = &oldest
	}
	return resp
}

// buildStats computes city-wide totals over non-CLOSED reports. Reports are
// assumed already window-filtered.
func buildStats(reports []Report, window string, now time.Time) StatsResponse {
	resp := StatsResponse{
		Window:                 window,
		GeneratedAt:            now.UTC().Format(iso8601),
		ByType:                 map[string]int{},
		BySeverity:             map[string]int{},
		AverageResolutionHours: map[string]float64{},
	}
	resSum := map[string]float64{}
	resCount := map[string]int{}

	for _, r := range reports {
		if r.Status == "CLOSED" {
			continue
		}
		switch r.Status {
		case "SUBMITTED":
			resp.Totals.Submitted++
		case "TRIAGED":
			resp.Totals.Triaged++
		case "IN_PROGRESS":
			resp.Totals.InProgress++
		case "RESOLVED":
			resp.Totals.Resolved++
		case "ESCALATED":
			resp.Totals.Escalated++
		}
		resp.ByType[r.Type]++
		resp.BySeverity[r.Severity]++
		if r.Status == "RESOLVED" {
			resSum[r.Severity] += r.UpdatedAt.Sub(r.CreatedAt).Hours()
			resCount[r.Severity]++
		}
	}
	for sev, sum := range resSum {
		resp.AverageResolutionHours[sev] = round1(sum / float64(resCount[sev]))
	}
	return resp
}

// buildStatsByType computes per-type breakdowns. An optional typeFilter narrows
// output to a single type.
func buildStatsByType(reports []Report, window, typeFilter string, now time.Time) StatsByTypeResponse {
	type acc struct {
		total, resolved int
		resHours        float64
		resCount        int
		bySeverity      map[string]int
	}
	byType := map[string]*acc{}
	for _, r := range reports {
		if r.Status == "CLOSED" {
			continue
		}
		if typeFilter != "" && r.Type != typeFilter {
			continue
		}
		a := byType[r.Type]
		if a == nil {
			a = &acc{bySeverity: map[string]int{}}
			byType[r.Type] = a
		}
		a.total++
		a.bySeverity[r.Severity]++
		if r.Status == "RESOLVED" {
			a.resolved++
			a.resHours += r.UpdatedAt.Sub(r.CreatedAt).Hours()
			a.resCount++
		}
	}

	types := make([]StatsByType, 0, len(byType))
	for t, a := range byType {
		entry := StatsByType{
			Type:       t,
			Total:      a.total,
			Resolved:   a.resolved,
			BySeverity: a.bySeverity,
		}
		if a.total > 0 {
			entry.ResolutionRatePct = round1(float64(a.resolved) / float64(a.total) * 100)
		}
		if a.resCount > 0 {
			entry.AverageResolutionHours = round1(a.resHours / float64(a.resCount))
		}
		types = append(types, entry)
	}
	sort.Slice(types, func(i, j int) bool { return types[i].Type < types[j].Type })

	return StatsByTypeResponse{Window: window, GeneratedAt: now.UTC().Format(iso8601), Types: types}
}

// buildHeatmap aggregates reports into ~100m grid cells (lat/lng rounded to 3
// decimals). Exact locations are never exposed.
func buildHeatmap(reports []Report, window string, now time.Time) HeatmapResponse {
	type cell struct {
		lat, lng   float64
		weight     int
		typeCounts map[string]int
		maxSevRank int
		maxSev     string
	}
	cells := map[string]*cell{}
	for _, r := range reports {
		if r.Status == "CLOSED" {
			continue
		}
		lat, lng := grid3(r.Location.Lat), grid3(r.Location.Lng)
		key := fmt.Sprintf("%.3f,%.3f", lat, lng)
		c := cells[key]
		if c == nil {
			c = &cell{lat: lat, lng: lng, typeCounts: map[string]int{}}
			cells[key] = c
		}
		c.weight++
		c.typeCounts[r.Type]++
		if severityRank[r.Severity] > c.maxSevRank {
			c.maxSevRank = severityRank[r.Severity]
			c.maxSev = r.Severity
		}
	}

	points := make([]HeatmapPoint, 0, len(cells))
	for _, c := range cells {
		points = append(points, HeatmapPoint{
			Lat:              c.lat,
			Lng:              c.lng,
			Weight:           c.weight,
			DominantType:     dominantType(c.typeCounts),
			DominantSeverity: c.maxSev,
		})
	}
	// Stable ordering: heaviest cells first, then by coordinate.
	sort.Slice(points, func(i, j int) bool {
		if points[i].Weight != points[j].Weight {
			return points[i].Weight > points[j].Weight
		}
		if points[i].Lat != points[j].Lat {
			return points[i].Lat < points[j].Lat
		}
		return points[i].Lng < points[j].Lng
	})

	return HeatmapResponse{Window: window, GeneratedAt: now.UTC().Format(iso8601), Points: points}
}

// dominantType returns the most frequent type in a cell, tie-broken by name for
// deterministic output.
func dominantType(counts map[string]int) string {
	best := ""
	bestN := -1
	for t, n := range counts {
		if n > bestN || (n == bestN && t < best) {
			best, bestN = t, n
		}
	}
	return best
}
