package main

import (
	"context"
	"encoding/json"
	"net/http"
	"net/url"
	"time"
)

// maxAggregateReports caps how many reports the stats/feed/heatmap endpoints
// pull from reports-service. A safety bound for a demo app — see logged warning
// when it truncates.
const maxAggregateReports = 2000

// Upstream calls reports-service and triage-service. It forwards trace headers on
// every request (Service Graph) and attaches the service token (harmless on the
// public reports endpoints, required by triage).
type Upstream struct {
	reportsURL string
	triageURL  string
	token      string
	hc         *http.Client
	log        *Logger
}

func NewUpstream(cfg Config, log *Logger) *Upstream {
	return &Upstream{
		reportsURL: cfg.ReportsServiceURL,
		triageURL:  cfg.TriageServiceURL,
		token:      cfg.ServiceToken,
		hc:         &http.Client{Timeout: 5 * time.Second},
		log:        log,
	}
}

func (u *Upstream) get(ctx context.Context, rawURL string, trace map[string]string) (*http.Response, error) {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, rawURL, nil)
	if err != nil {
		return nil, err
	}
	if u.token != "" {
		req.Header.Set("X-Service-Token", u.token)
	}
	for k, v := range trace {
		req.Header.Set(k, v)
	}
	return u.hc.Do(req)
}

// GetReport fetches a single report. Returns errNotFound on 404 and errUpstream
// on connection failure or 5xx.
func (u *Upstream) GetReport(ctx context.Context, id string, trace map[string]string) (*Report, *apiError) {
	resp, err := u.get(ctx, u.reportsURL+"/reports/"+url.PathEscape(id), trace)
	if err != nil {
		return nil, aptr(errUpstream("Unable to retrieve report status. reports-service is currently unavailable. Please try again shortly."))
	}
	defer resp.Body.Close()

	if resp.StatusCode == http.StatusNotFound {
		return nil, aptr(errNotFound("No report found with ID " + id + "."))
	}
	if resp.StatusCode >= 400 {
		return nil, aptr(errUpstream("reports-service returned an unexpected error. Please try again shortly."))
	}

	var rep Report
	if err := json.NewDecoder(resp.Body).Decode(&rep); err != nil {
		return nil, aptr(errUpstream("Malformed response from reports-service."))
	}
	return &rep, nil
}

// FetchReports pages through the reports-service list endpoint (applying the
// given filters) up to maxAggregateReports.
func (u *Upstream) FetchReports(ctx context.Context, filters url.Values, trace map[string]string) ([]Report, *apiError) {
	all := make([]Report, 0, 128)
	offset := 0
	const pageSize = 100

	for {
		q := url.Values{}
		for k, vs := range filters {
			for _, v := range vs {
				q.Add(k, v)
			}
		}
		q.Set("limit", itoa(pageSize))
		q.Set("offset", itoa(offset))

		resp, err := u.get(ctx, u.reportsURL+"/reports?"+q.Encode(), trace)
		if err != nil {
			return nil, aptr(errUpstream("Unable to retrieve incidents. reports-service is currently unavailable. Please try again shortly."))
		}
		var list ReportList
		decErr := json.NewDecoder(resp.Body).Decode(&list)
		status := resp.StatusCode
		resp.Body.Close()
		if status >= 400 {
			return nil, aptr(errUpstream("reports-service returned an unexpected error. Please try again shortly."))
		}
		if decErr != nil {
			return nil, aptr(errUpstream("Malformed response from reports-service."))
		}

		all = append(all, list.Reports...)
		offset += len(list.Reports)
		if len(list.Reports) == 0 || offset >= list.Total || len(all) >= maxAggregateReports {
			if len(all) >= maxAggregateReports && offset < list.Total {
				u.log.Warn("Aggregate report cap reached; statistics computed over a partial sample.",
					map[string]any{"cap": maxAggregateReports, "total": list.Total})
			}
			break
		}
	}
	if len(all) > maxAggregateReports {
		all = all[:maxAggregateReports]
	}
	return all, nil
}

// Ping is a liveness probe used by the health endpoint. baseURL is the service's
// /v1 base. Returns "healthy" | "unhealthy".
func (u *Upstream) Ping(ctx context.Context, baseURL string, trace map[string]string) string {
	req, err := http.NewRequestWithContext(ctx, http.MethodGet, baseURL+"/health", nil)
	if err != nil {
		return "unhealthy"
	}
	// X-Health-Probe tells the peer to answer shallowly (local deps only), so peer
	// /health checks don't recurse into each other.
	req.Header.Set("X-Health-Probe", "1")
	for k, v := range trace {
		req.Header.Set(k, v)
	}
	resp, err := u.hc.Do(req)
	if err != nil {
		return "unhealthy"
	}
	defer resp.Body.Close()
	if resp.StatusCode < 500 {
		return "healthy"
	}
	return "unhealthy"
}
