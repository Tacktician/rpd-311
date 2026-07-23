package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"time"

	"github.com/go-chi/chi/v5"
)

// GET /v1/status/{reportId} — cache-first public status (30s TTL).
func (a *App) handleStatus(w http.ResponseWriter, r *http.Request) {
	id := chi.URLParam(r, "reportId")
	a.serveCached(w, r, "status:"+id, a.cfg.TTLStatus, func() (any, *apiError) {
		rep, aerr := a.up.GetReport(r.Context(), id, traceHeadersFrom(r))
		if aerr != nil {
			return nil, aerr
		}
		public, ok := mapPublicStatus(rep.Status)
		if !ok {
			// CLOSED reports are not exposed publicly.
			return nil, aptr(errNotFound("No report found with ID " + id + "."))
		}
		return PublicStatusResponse{
			ReportID:              rep.ReportID,
			Type:                  rep.Type,
			Status:                public,
			Severity:              rep.Severity,
			Location:              rep.Location,
			SubmittedAt:           rep.CreatedAt.UTC().Format(iso8601),
			UpdatedAt:             rep.UpdatedAt.UTC().Format(iso8601),
			EstimatedResponseTime: estimatedResponseTime(rep.Severity, public),
			PublicNote:            nil,
		}, nil
	})
}

// GET /v1/feed — paginated public feed (60s TTL).
func (a *App) handleFeed(w http.ResponseWriter, r *http.Request) {
	q := r.URL.Query()
	now := time.Now()

	// Collect validation errors via a helper that short-circuits on the first.
	var firstErr *apiError
	check := func(e *apiError) {
		if firstErr == nil {
			firstErr = e
		}
	}

	typ, e := optEnum(q, "type", incidentTypes)
	check(e)
	sev, e := optEnum(q, "severity", severityLevels)
	check(e)
	st, e := optEnum(q, "status", publicStatuses)
	check(e)
	lat, hasLat, e := optFloat(q, "lat", -90, 90)
	check(e)
	lng, hasLng, e := optFloat(q, "lng", -180, 180)
	check(e)
	radius, e := optInt(q, "radius", 5000, 1, 50000)
	check(e)
	limit, e := optInt(q, "limit", 20, 1, 100)
	check(e)
	offset, e := optInt(q, "offset", 0, 0, maxOffset)
	check(e)
	since, e := optSince(q, now)
	check(e)

	if firstErr != nil {
		writeError(w, r, *firstErr)
		return
	}
	if hasLat != hasLng {
		writeError(w, r, errBadRequest("Location filtering requires both 'lat' and 'lng'."))
		return
	}

	// Normalized cache key (stable regardless of client param order).
	ck := url.Values{}
	putIf(ck, "type", typ)
	putIf(ck, "severity", sev)
	putIf(ck, "status", st)
	if hasLat {
		ck.Set("lat", ftoa(lat))
		ck.Set("lng", ftoa(lng))
		ck.Set("radius", itoa(radius))
	}
	ck.Set("limit", itoa(limit))
	ck.Set("offset", itoa(offset))
	if !since.IsZero() {
		ck.Set("since", since.UTC().Format(iso8601))
	}

	a.serveCached(w, r, "feed:"+ck.Encode(), a.cfg.TTLFeed, func() (any, *apiError) {
		up := url.Values{}
		putIf(up, "type", typ)
		putIf(up, "severity", sev)
		if hasLat {
			up.Set("lat", ftoa(lat))
			up.Set("lng", ftoa(lng))
			up.Set("radius", itoa(radius))
		}
		reports, aerr := a.up.FetchReports(r.Context(), up, traceHeadersFrom(r))
		if aerr != nil {
			return nil, aerr
		}
		return buildFeed(reports, feedFilter{
			incidentType: typ, severity: sev, status: st, since: since, limit: limit, offset: offset,
		}), nil
	})
}

// GET /v1/stats — city-wide statistics (5min TTL).
func (a *App) handleStats(w http.ResponseWriter, r *http.Request) {
	now := time.Now()
	window, e := optWindow(r.URL.Query(), statsWindows, "30d")
	if e != nil {
		writeError(w, r, *e)
		return
	}
	a.serveCached(w, r, "stats:"+window, a.cfg.TTLStats, func() (any, *apiError) {
		reports, aerr := a.up.FetchReports(r.Context(), url.Values{}, traceHeadersFrom(r))
		if aerr != nil {
			return nil, aerr
		}
		return buildStats(filterByWindow(reports, window, now), window, now), nil
	})
}

// GET /v1/stats/by-type — per-type breakdown (5min TTL).
func (a *App) handleStatsByType(w http.ResponseWriter, r *http.Request) {
	now := time.Now()
	q := r.URL.Query()
	window, e := optWindow(q, statsWindows, "30d")
	if e != nil {
		writeError(w, r, *e)
		return
	}
	typ, e := optEnum(q, "type", incidentTypes)
	if e != nil {
		writeError(w, r, *e)
		return
	}
	a.serveCached(w, r, "stats:bytype:"+window+":"+typ, a.cfg.TTLStats, func() (any, *apiError) {
		up := url.Values{}
		putIf(up, "type", typ)
		reports, aerr := a.up.FetchReports(r.Context(), up, traceHeadersFrom(r))
		if aerr != nil {
			return nil, aerr
		}
		return buildStatsByType(filterByWindow(reports, window, now), window, typ, now), nil
	})
}

// GET /v1/stats/heatmap — location heatmap (10min TTL).
func (a *App) handleHeatmap(w http.ResponseWriter, r *http.Request) {
	now := time.Now()
	q := r.URL.Query()
	window, e := optWindow(q, heatmapWindows, "7d")
	if e != nil {
		writeError(w, r, *e)
		return
	}
	typ, e := optEnum(q, "type", incidentTypes)
	if e != nil {
		writeError(w, r, *e)
		return
	}
	sev, e := optEnum(q, "severity", severityLevels)
	if e != nil {
		writeError(w, r, *e)
		return
	}
	a.serveCached(w, r, "heatmap:"+window+":"+typ+":"+sev, a.cfg.TTLHeatmap, func() (any, *apiError) {
		up := url.Values{}
		putIf(up, "type", typ)
		putIf(up, "severity", sev)
		reports, aerr := a.up.FetchReports(r.Context(), up, traceHeadersFrom(r))
		if aerr != nil {
			return nil, aerr
		}
		return buildHeatmap(filterByWindow(reports, window, now), window, now), nil
	})
}

// POST /v1/internal/cache/invalidate — internal only (service token).
func (a *App) handleInvalidate(w http.ResponseWriter, r *http.Request) {
	var body struct {
		ReportID string `json:"reportId"`
		Reason   string `json:"reason"`
	}
	if err := json.NewDecoder(r.Body).Decode(&body); err != nil {
		writeError(w, r, errBadRequest("Request body is not valid JSON."))
		return
	}
	if body.ReportID == "" {
		writeError(w, r, errBadRequest("The 'reportId' field is required."))
		return
	}

	evicted := a.cache.Del(r.Context(), "status:"+body.ReportID)
	a.log.Info("Cache invalidation processed.", map[string]any{
		"reportId": body.ReportID, "evicted": evicted, "reason": body.Reason,
	})

	msg := "Cache entry evicted for report " + body.ReportID
	if !evicted {
		msg = "No cache entry present for report " + body.ReportID + "; nothing to evict."
	}
	writeJSON(w, http.StatusOK, map[string]any{
		"reportId": body.ReportID,
		"evicted":  evicted,
		"message":  msg,
	})
}

// GET /v1/health — no auth. Redis outage => degraded (200); upstream outage => unhealthy (503).
func (a *App) handleHealth(w http.ResponseWriter, r *http.Request) {
	ctx, cancel := context.WithTimeout(r.Context(), 2*time.Second)
	defer cancel()
	trace := traceHeadersFrom(r)

	redis := "healthy"
	if err := a.cache.Ping(ctx); err != nil {
		redis = "unhealthy"
	}
	reports := a.up.Ping(ctx, a.cfg.ReportsServiceURL, trace)
	triage := a.up.Ping(ctx, a.cfg.TriageServiceURL, trace)

	overall, code := "healthy", http.StatusOK
	if reports != "healthy" || triage != "healthy" {
		overall, code = "unhealthy", http.StatusServiceUnavailable
	} else if redis != "healthy" {
		overall = "degraded"
	}

	writeJSON(w, code, HealthResponse{
		Status:    overall,
		Service:   "status-service",
		Version:   "1.0.0",
		Timestamp: time.Now().UTC().Format(iso8601),
		Dependencies: map[string]string{
			"redis": redis, "reportsService": reports, "triageService": triage,
		},
	})
}

func putIf(v url.Values, key, val string) {
	if val != "" {
		v.Set(key, val)
	}
}
