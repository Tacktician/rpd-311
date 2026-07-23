package main

import (
	"context"
	"encoding/json"
	"net/http"
	"time"

	"github.com/redis/go-redis/v9"
)

// Cache is a thin Redis wrapper that degrades gracefully: any Redis error is
// treated as a miss / no-op so the service keeps serving from upstream. A nil
// client (unparseable URL) disables caching entirely.
type Cache struct {
	rdb *redis.Client
	log *Logger
}

type cacheEntry struct {
	CachedAt int64           `json:"cachedAt"`
	Body     json.RawMessage `json:"body"`
}

func NewCache(url string, log *Logger) *Cache {
	opt, err := redis.ParseURL(url)
	if err != nil {
		log.Warn("Invalid REDIS_URL — cache disabled, serving upstream-only.", map[string]any{"error": err.Error()})
		return &Cache{log: log}
	}
	return &Cache{rdb: redis.NewClient(opt), log: log}
}

// Get returns the cached body and its age in seconds. hit is false on miss,
// disabled cache, or any Redis error.
func (c *Cache) Get(ctx context.Context, key string) (body []byte, ageSeconds int, hit bool) {
	if c.rdb == nil {
		return nil, 0, false
	}
	raw, err := c.rdb.Get(ctx, key).Bytes()
	if err != nil {
		if err != redis.Nil {
			c.log.Debug("Redis GET failed; treating as cache miss.", map[string]any{"error": err.Error()})
		}
		return nil, 0, false
	}
	var entry cacheEntry
	if err := json.Unmarshal(raw, &entry); err != nil {
		return nil, 0, false
	}
	age := int(time.Now().Unix() - entry.CachedAt)
	if age < 0 {
		age = 0
	}
	return entry.Body, age, true
}

func (c *Cache) Set(ctx context.Context, key string, body []byte, ttl time.Duration) {
	if c.rdb == nil {
		return
	}
	entry, err := json.Marshal(cacheEntry{CachedAt: time.Now().Unix(), Body: body})
	if err != nil {
		return
	}
	if err := c.rdb.Set(ctx, key, entry, ttl).Err(); err != nil {
		c.log.Debug("Redis SET failed; response served but not cached.", map[string]any{"error": err.Error()})
	}
}

func (c *Cache) Del(ctx context.Context, key string) bool {
	if c.rdb == nil {
		return false
	}
	n, err := c.rdb.Del(ctx, key).Result()
	if err != nil {
		c.log.Debug("Redis DEL failed.", map[string]any{"error": err.Error()})
		return false
	}
	return n > 0
}

func (c *Cache) Ping(ctx context.Context) error {
	if c.rdb == nil {
		return redis.ErrClosed
	}
	return c.rdb.Ping(ctx).Err()
}

func writeRaw(w http.ResponseWriter, status int, body []byte) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_, _ = w.Write(body)
}

// serveCached implements the cache-first pattern shared by all read endpoints:
// return a HIT, or build fresh, cache it, and return a MISS. Both paths set the
// X-Cache and X-Cache-Age headers required by the spec.
func (a *App) serveCached(
	w http.ResponseWriter,
	r *http.Request,
	key string,
	ttl time.Duration,
	build func() (any, *apiError),
) {
	if body, age, hit := a.cache.Get(r.Context(), key); hit {
		w.Header().Set("X-Cache", "HIT")
		w.Header().Set("X-Cache-Age", itoa(age))
		writeRaw(w, http.StatusOK, body)
		return
	}

	payload, aerr := build()
	if aerr != nil {
		writeError(w, r, *aerr)
		return
	}
	body, err := json.Marshal(payload)
	if err != nil {
		writeError(w, r, apiError{http.StatusInternalServerError, "INTERNAL_ERROR", "Failed to encode response."})
		return
	}
	a.cache.Set(r.Context(), key, body, ttl)
	w.Header().Set("X-Cache", "MISS")
	w.Header().Set("X-Cache-Age", "0")
	writeRaw(w, http.StatusOK, body)
}
