package main

import (
	"os"
	"strconv"
	"time"
)

// Config is read from the environment. Values are injected via Kubernetes
// (see k8s/base/) in-cluster, or docker-compose.local.yml locally.
type Config struct {
	Port              string
	RedisURL          string
	ServiceToken      string
	ReportsServiceURL string
	TriageServiceURL  string
	TTLStatus         time.Duration
	TTLFeed           time.Duration
	TTLStats          time.Duration
	TTLHeatmap        time.Duration
	TraceEnabled      bool
	LogLevel          string
}

func getenv(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func getenvInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func getenvBool(key string, def bool) bool {
	switch os.Getenv(key) {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return def
	}
}

// LoadConfig builds Config from the environment with sane local defaults.
func LoadConfig() Config {
	return Config{
		Port:              getenv("PORT", "3003"),
		RedisURL:          getenv("REDIS_URL", "redis://redis:6379"),
		ServiceToken:      os.Getenv("SERVICE_TOKEN"),
		ReportsServiceURL: getenv("REPORTS_SERVICE_URL", "http://reports-service:3001/v1"),
		TriageServiceURL:  getenv("TRIAGE_SERVICE_URL", "http://triage-service:3002/v1"),
		TTLStatus:         time.Duration(getenvInt("CACHE_TTL_STATUS_SECONDS", 30)) * time.Second,
		TTLFeed:           time.Duration(getenvInt("CACHE_TTL_FEED_SECONDS", 60)) * time.Second,
		TTLStats:          time.Duration(getenvInt("CACHE_TTL_STATS_SECONDS", 300)) * time.Second,
		TTLHeatmap:        time.Duration(getenvInt("CACHE_TTL_HEATMAP_SECONDS", 600)) * time.Second,
		TraceEnabled:      getenvBool("TRACEPARENT_PROPAGATION_ENABLED", true),
		LogLevel:          getenv("LOG_LEVEL", "info"),
	}
}
