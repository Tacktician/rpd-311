package main

import (
	"math"
	"net/url"
	"strconv"
	"time"
)

var statsWindows = map[string]bool{"24h": true, "7d": true, "30d": true, "90d": true, "all": true}
var heatmapWindows = map[string]bool{"24h": true, "7d": true, "30d": true}

func optEnum(q url.Values, name string, set map[string]bool) (string, *apiError) {
	v := q.Get(name)
	if v == "" {
		return "", nil
	}
	if !set[v] {
		return "", aptr(errBadRequest("Query parameter '" + name + "' is not a recognized value."))
	}
	return v, nil
}

func optInt(q url.Values, name string, def, min, max int) (int, *apiError) {
	v := q.Get(name)
	if v == "" {
		return def, nil
	}
	n, err := strconv.Atoi(v)
	if err != nil || n < min || n > max {
		return 0, aptr(errBadRequest("Query parameter '" + name + "' must be an integer between " + itoa(min) + " and " + itoa(max) + "."))
	}
	return n, nil
}

// optFloat reports whether the param was present so callers can enforce
// lat/lng-together rules.
func optFloat(q url.Values, name string, min, max float64) (float64, bool, *apiError) {
	v := q.Get(name)
	if v == "" {
		return 0, false, nil
	}
	f, err := strconv.ParseFloat(v, 64)
	if err != nil || f < min || f > max {
		return 0, false, aptr(errBadRequest("Query parameter '" + name + "' must be a number between " + ftoa(min) + " and " + ftoa(max) + "."))
	}
	return f, true, nil
}

func optWindow(q url.Values, allowed map[string]bool, def string) (string, *apiError) {
	v := q.Get("window")
	if v == "" {
		return def, nil
	}
	if !allowed[v] {
		return "", aptr(errBadRequest("Query parameter 'window' is not a recognized value."))
	}
	return v, nil
}

// optSince parses the feed 'since' timestamp. Absent -> zero time. Lookback is
// clamped to 7 days per the spec.
func optSince(q url.Values, now time.Time) (time.Time, *apiError) {
	v := q.Get("since")
	if v == "" {
		return time.Time{}, nil
	}
	t, err := time.Parse(time.RFC3339, v)
	if err != nil {
		return time.Time{}, aptr(errBadRequest("Query parameter 'since' must be an RFC 3339 timestamp."))
	}
	if earliest := now.AddDate(0, 0, -7); t.Before(earliest) {
		t = earliest // clamp: maximum lookback is 7 days
	}
	return t, nil
}

const maxOffset = math.MaxInt32
