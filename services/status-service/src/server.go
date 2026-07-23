package main

import (
	"net/http"

	"github.com/go-chi/chi/v5"
)

// App bundles the dependencies shared by all handlers.
type App struct {
	cfg   Config
	cache *Cache
	up    *Upstream
	log   *Logger
}

func NewApp(cfg Config, cache *Cache, up *Upstream, log *Logger) *App {
	return &App{cfg: cfg, cache: cache, up: up, log: log}
}

// Router wires routes under /v1 to match the OpenAPI `servers` base path. All
// read endpoints are public; only cache invalidation requires a service token.
func (a *App) Router() http.Handler {
	r := chi.NewRouter()
	r.Use(requestIDMiddleware)
	r.Use(a.tracingMiddleware)

	r.Route("/v1", func(r chi.Router) {
		r.Get("/status/{reportId}", a.handleStatus)
		r.Get("/feed", a.handleFeed)
		r.Get("/stats", a.handleStats)
		r.Get("/stats/by-type", a.handleStatsByType)
		r.Get("/stats/heatmap", a.handleHeatmap)
		r.Get("/health", a.handleHealth)

		r.Group(func(r chi.Router) {
			r.Use(a.serviceTokenMiddleware)
			r.Post("/internal/cache/invalidate", a.handleInvalidate)
		})
	})

	return r
}
