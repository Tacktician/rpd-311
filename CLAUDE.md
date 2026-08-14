# CLAUDE.md — RPD 311

This file gives Claude Code the context needed to implement the RPD 311 demo application.
Read this before touching any code.

---

## What this is

RPD 311 is a **fictional civic incident reporting platform for Raccoon City** (from Resident Evil).
It is a demo application built to demonstrate Kubernetes deployment and Postman API Catalog
service discovery — specifically the Postman Insights Agent and Cluster Watcher.

The app is intentionally deadpan. Residents submit reports of noise complaints, potholes,
car break-ins, zombie sightings, and Umbrella Corporation activity. The platform triages
reports and routes them to the appropriate city department. All of this is treated with
complete bureaucratic seriousness in the code, comments, and error messages.

---

## Repo structure

```
rpd311/
├── services/
│   ├── reports-service/     Node.js / Express  — port 3001  (public write API)
│   ├── triage-service/      Python / FastAPI    — port 3002  (internal only, no ingress)
│   └── status-service/      Go                 — port 3003  (public read API)
├── k8s/                     Kubernetes manifests (complete — do not modify without reason)
│   └── prod/                the only EKS-specific manifests (ingress + secret script)
├── infra/terraform/         EKS prod cluster; bootstrap/ holds the tfstate bucket + OIDC role
├── docker-compose.yml       Base deps (Postgres, Redis, LocalStack)
├── docker-compose.local.yml Local dev overrides
└── CLAUDE.md                This file
```

---

## What is already done

- **OpenAPI specs** — complete for all three services. These are the source of truth.
  Before implementing any endpoint, read the spec for that service first.
  - `services/reports-service/openapi.yaml`
  - `services/triage-service/openapi.yaml`
  - `services/status-service/openapi.yaml`

- **Dockerfiles** — placeholder multi-stage builds exist for all three services.
  They are structurally correct but may need adjustment once `src/` has real code.

- **Kubernetes manifests** — complete and ready for deployment. Do not modify these
  unless a service implementation decision forces a change (e.g. a new env var is needed —
  add it to `k8s/base/configmap-common.yaml`).

- **Architecture roadmap** — see `README.md` for the full service breakdown, incident
  type routing table, and infrastructure overview.

---

## Current state (read first)

Implementation progress:

- **reports-service** — ✅ implemented (Node.js/Express, ES modules). All endpoints,
  W3C tracing, service-token auth, S3 attachments, Postgres schema auto-migrate on boot,
  and unit tests (`npm test`). See `services/reports-service/src/`.
- **triage-service** — ✅ implemented (Python 3.12/FastAPI, asyncpg, httpx). All
  endpoints, routing engine (`src/routing.py`), W3C tracing, service-token auth on
  every endpoint, reports-service status callbacks, schema auto-migrate on boot, and
  unit tests (`pytest`). See `services/triage-service/src/`.
- **status-service** — ✅ implemented (Go 1.22, chi router, go-redis). All endpoints,
  cache-first Redis with graceful degradation + `X-Cache`/`X-Cache-Age` headers, public
  status mapping, stats/heatmap aggregation, W3C tracing, service-token guard on cache
  invalidation, and unit tests (`go test ./src/...`). Single `main` package under `src/`
  (keeps `go build -o status-service ./src/...` clean). See `services/status-service/src/`.
- `docker-compose.yml` / `docker-compose.local.yml` — ✅ present (deps + app containers)

All three services are now implemented and verified end-to-end via docker-compose
(build → submit → triage callback → acknowledge → public status/feed/stats/heatmap →
S3 attachment upload). CI/CD is wired up in `.github/workflows/`:
- **ci.yaml** (push/PR to main): per-service unit test + lint (Node `npm test`; Python
  `pytest`; Go `gofmt`/`vet`/`test`/`build`), a docker build of all three images (validates
  the Dockerfiles and warms the layer cache `deploy-prod` reuses), an **`integration` job**
  that boots the full compose stack and runs the cross-service E2E suite, a
  **`minikube-e2e` job** that stands up a real cluster and runs the same suite against it,
  and a **`deploy-prod` job** gated on all three.
- **teardown.yaml** (`workflow_dispatch` only): `terraform destroy` of the prod cluster,
  requiring the cluster name typed as confirmation.

`deploy-prod` **self-skips unless the `AWS_ROLE_ARN` and `TF_STATE_BUCKET` repo variables
are both set**, so CI stays green with no cloud credentials configured. Preserve that
property in any CI change — it is what keeps the repo cloneable and testable by learners
who have no AWS account.
- **`e2e/`** — one HTTP harness, two jobs: `test_flow.py` (integration tests over the
  live reports→triage→status flow + real Postgres/Redis/LocalStack, run by CI) and
  `generate_traffic.py` (same flows on a loop, to feed the Insights Agent a connected
  Service Graph). Config via `REPORTS_URL`/`TRIAGE_URL`/`STATUS_URL`/`SERVICE_TOKEN`
  env (defaults match compose). Note: `/feed` and `/stats` are cached and not
  write-invalidated, so tests assert on populated/mapped state, not post-write deltas.

### Environments

| | Where | Role |
|---|---|---|
| Local | docker-compose | Fast loop for service code. |
| Local cluster | minikube / kind | **Rehearsal for prod.** Images built locally + `minikube image load`; no registry. |
| Prod | EKS `rpd311-prod` | **Deploy destination.** `infra/terraform/`; images from ECR, tagged with the commit SHA. |

The two clusters run the **same images, the same manifests, and the same in-cluster
Postgres/Redis/LocalStack** (`k8s/dev/datastores.yaml`). Only `k8s/prod/` differs — two
files: `ingress-prod.yaml` (identical to `ingress-local.yaml` except it omits the `host:`
rule, so the NLB DNS name works without a domain or ACM) and `create-secret.sh` (builds
the Secret from CI secrets instead of the committed `changeme-service-token` in
`base/secret-local.yaml`).

That near-identity is load-bearing, not incidental: `deploy-prod` is gated on
`minikube-e2e` passing the full E2E suite on a real cluster. **Every new prod-only file
weakens the gate** — if a change needs one, prefer making the shared manifest work in both
places. Prod deliberately has no RDS, ElastiCache, real S3, ACM, Route 53, ALB, IRSA, or
External Secrets Operator; see `infra/terraform/README.md` for the reasoning and the
~$0.21/hour cost breakdown.

The prod cluster is **not always up** — the teardown workflow destroys it between demos
and the next merge to `main` rebuilds it (15–20 min for the control plane and node group).
Terraform state lives in S3 so a destroy leaves a clean slate. `infra/terraform/bootstrap/`
(state bucket + GitHub OIDC role) keeps local state and is never torn down.

Integration caveats learned from the compose run (all fixed in-tree unless noted):
- **Cross-service `/health` must not recurse.** Peer connectivity checks send an
  `X-Health-Probe` header; a `/health` that sees it answers shallowly (local deps only).
  Without this, `reports↔triage` health checks mutually recurse until timeouts fire.
- **reports→triage forward payload** must match triage's `TriageRequest` exactly
  (`submitterSeverity` not `severity`, plus required `receivedAt`) — triage forbids extra fields.
- **Immediate-escalation reports** (`UMBRELLA_CORP_ACTIVITY`) call back with status
  `ESCALATED`; all others with `TRIAGED`.
- **LocalStack** must be pinned to `localstack/localstack:3` — the unpinned `:latest`
  now resolves to a license-gated Pro build that exits 55 without an auth token.
- **Hot reload doesn't work on macOS bind mounts** (inotify doesn't cross the Docker
  Desktop VM). After editing `reports`/`triage` source, `docker compose restart <svc>`;
  rebuild `status` (compiled Go binary).
- **Known simplifications** (not bugs — inherent to the OpenAPI contracts): the report's
  stored `severity` keeps the submitter value (the PATCH-status contract carries no
  severity field; the authoritative severity lives on the triage assignment), and
  LocalStack presigned URLs embed the in-container `localstack:4566` host (fine for the
  local demo — the URL is reachable from inside the cluster / compose network).

Kubernetes / minikube (validated end-to-end — full flow + ingress + HPA + S3):
- **In-cluster datastores**: `k8s/dev/datastores.yaml` provides Postgres/Redis/
  LocalStack (service names match `secret-local.yaml` hosts). Apply it as part of the
  local bring-up — the app deployments connect to these by DNS name.
- **Manifest bugs fixed** (were in the pre-existing manifests): `secret-local.yaml`
  `REDIS_URL` port `3792`→`6379`; ingress `rewrite-target` `/$1`→`/v1/$1` (services serve
  under `/v1`, so stripping it 404s); `postman.com/openapi-path: "/openapi.yaml"` moved
  from a label to an annotation on reports+status deployments (label values can't contain `/`).
- **Concurrent-replica migration race** (found on minikube): simultaneous
  `CREATE EXTENSION/TYPE IF NOT EXISTS` from multiple replicas races on the pg catalog
  unique index and crashes a pod on first boot. Fixed with a Postgres advisory lock around
  migration (reports `db/migrate.js`, triage `db.py`).
- **ingress-nginx snippets — removed, do not re-add.** Modern ingress-nginx (including the
  version the minikube `ingress` addon installs) *rejects* `configuration-snippet` at the
  admission webhook: "Snippet directives are disabled by the Ingress administrator". This
  failed the `minikube-e2e` job. Both ingresses now omit it. Re-enabling would need BOTH
  `allow-snippet-annotations: "true"` and `annotations-risk-level: "Critical"` in the
  controller ConfigMap — pointless ceremony, since nginx forwards
  `traceparent`/`tracestate` to upstreams by default and the snippet never did any work.
- **Ingress class** goes in `spec.ingressClassName`, not the deprecated
  `kubernetes.io/ingress.class` annotation (which warns on every apply).
- **Pin the minikube Kubernetes version.** `minikube start` unpinned tracks the newest
  upstream release (it pulled 1.35.1 in CI), so the gate would test a control plane three
  minors ahead of prod. CI pins `v1.32.0` to match `infra/terraform/variables.tf`
  `kubernetes_version`. Bump both together or the gate stops being faithful.
- **Local run recipe**: build `rpd311/<svc>:1.0.0` + `minikube image load` (deployments use
  `imagePullPolicy: IfNotPresent`); apply base → `k8s/dev/datastores.yaml` → services →
  `ingress-local.yaml`. On the macOS docker driver the ingress isn't directly routable —
  reach it via `kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 18080:80`
  and send `Host: rpd311.local`. triage-service correctly 404s through the ingress (no
  public rule) while remaining reachable in-cluster.

Local toolchain notes (this machine only — the Docker builds are unaffected):
- **Python**: system is 3.14 but the stack targets 3.12. Use `uv venv --python 3.12`
  (uv is installed) for triage-service — pinned `asyncpg`/`pydantic-core` lack 3.14 wheels.
- **Go**: the stack targets 1.22 (Dockerfile), but this macOS (Darwin 25.5) is too new for
  Go 1.22's linker — test binaries abort with a `missing LC_UUID` dyld error. Compilation
  under 1.22 is fine; to *run* tests/binary locally use Go ≥1.23. `go.mod` stays at 1.22.

### Build & run (entrypoints the Dockerfiles expect)

| Service | Entrypoint the Dockerfile runs | Build / run |
|---|---|---|
| reports-service | `node src/index.js` | `npm ci && node src/index.js` |
| triage-service | `uvicorn src.main:app --host 0.0.0.0 --port 3002` | `pip install -r requirements.txt && uvicorn src.main:app --reload` |
| status-service | compiled `status-service` binary (`go build ./src/...`) | `go run ./src/...` |

- Container image build (per service): `docker build -t rpd311-<name> services/<name>/`
- Local dependencies + full stack + smoke tests: see the **Quick start (local)** section in `README.md`
  (`docker compose ... up -d`, then `minikube` + `kubectl apply -f k8s/...`).
- Tests (once written): Node.js → `npm test` (Jest + supertest); Python → `pytest`
  (httpx); Go → `go test ./...` (stdlib `testing` + `httptest`). Run a single test with
  `npx jest -t "<name>"`, `pytest -k "<name>"`, or `go test -run "<Name>" ./...`.

---

## What needs to be built

### 1. `docker-compose.yml` + `docker-compose.local.yml`

Base dependencies for local development:

| Dependency | Image | Purpose |
|---|---|---|
| Postgres 15 | `postgres:15-alpine` | reports-service and triage-service databases |
| Redis 7 | `redis:7-alpine` | status-service cache layer |
| LocalStack | `localstack/localstack` | S3 for photo attachments (reports-service) |

`docker-compose.yml` — base services only (deps, no app containers).
`docker-compose.local.yml` — overrides for local dev: exposed ports, volume mounts,
hot-reload for each service container.

### 2. `services/reports-service/src/`

**Stack:** Node.js 20, Express, Postgres (`pg` or `drizzle-orm`), AWS SDK v3 (S3).

Implement all endpoints defined in `services/reports-service/openapi.yaml`:

| Method | Path | Notes |
|---|---|---|
| `POST` | `/v1/reports` | Validate body, insert to Postgres, forward to triage-service |
| `GET` | `/v1/reports` | Paginated list with filters (type, status, severity, location radius) |
| `GET` | `/v1/reports/:reportId` | Public — redact sensitive fields for unauthed callers |
| `PATCH` | `/v1/reports/:reportId/status` | Internal only — validate X-Service-Token header |
| `POST` | `/v1/reports/:reportId/attachments` | Multipart upload → S3 → return pre-signed URL |
| `GET` | `/v1/reports/:reportId/attachments` | List attachments with pre-signed URLs |
| `GET` | `/v1/health` | Check Postgres + S3 + triage-service connectivity |

**Key implementation details:**
- On `POST /v1/reports`, after inserting to Postgres, fire a `POST` to
  `triage-service /v1/triage` with the new report. Do not await the triage response
  before returning 201 to the caller — fire and move on (or use a short timeout).
- On `PATCH /v1/reports/:reportId/status`, validate `X-Service-Token` header against
  the `SERVICE_TOKEN` env var. Reject with 401 if missing or wrong.
- W3C tracing: read `traceparent` from incoming request headers and forward it on
  every outbound HTTP call (to triage-service and status-service cache invalidation).
  This is required for the Postman API Catalog Service Graph to populate.
- Pre-signed S3 URLs should be valid for 24 hours.
- Location radius filtering: use the Haversine formula or Postgres `earthdistance`
  extension. Keep it simple — this is a demo app.

**Environment variables** (injected via K8s — see `k8s/base/`):
```
PORT                    3001
POSTGRES_HOST
POSTGRES_PORT           5432
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB_REPORTS     reports
S3_BUCKET_NAME          rpd311-attachments
S3_REGION               us-east-1
S3_ENDPOINT_URL         (points at LocalStack, e.g. http://localstack:4566)
AWS_ACCESS_KEY_ID       (LocalStack: "test")
AWS_SECRET_ACCESS_KEY   (LocalStack: "test")
SERVICE_TOKEN           (for validating triage/status callbacks)
TRIAGE_SERVICE_URL      http://triage-service.rpd311.svc.cluster.local/v1
STATUS_SERVICE_URL      http://status-service.rpd311.svc.cluster.local/v1
TRACEPARENT_PROPAGATION_ENABLED  true
```

### 3. `services/triage-service/src/`

**Stack:** Python 3.12, FastAPI, asyncpg (or SQLAlchemy async), httpx.

Implement all endpoints defined in `services/triage-service/openapi.yaml`:

| Method | Path | Notes |
|---|---|---|
| `POST` | `/v1/triage` | Classify report, persist assignment, callback to reports-service |
| `POST` | `/v1/triage/batch` | Batch variant — process up to 50, CRITICAL types first |
| `GET` | `/v1/assignments/:reportId` | Return routing decision for a report |
| `GET` | `/v1/queue/:department` | Paginated queue for a department, CRITICAL first |
| `POST` | `/v1/queue/:department/assignments/:assignmentId/acknowledge` | Acknowledge + callback to reports-service |
| `GET` | `/v1/health` | Check Postgres + reports-service connectivity |

**Routing logic** — implement this exactly. The enum values must match the OpenAPI spec:

```python
ROUTING_TABLE = {
    "POTHOLE":                  {"severity": "LOW",      "departments": ["PUBLIC_WORKS"]},
    "DOWNED_TREE":              {"severity": "LOW",      "departments": ["PUBLIC_WORKS"]},
    "NOISE_COMPLAINT":          {"severity": "MEDIUM",   "departments": ["RPD_NON_EMERGENCY"]},
    "SUSPICIOUS_PERSON":        {"severity": "MEDIUM",   "departments": ["RPD_NON_EMERGENCY"]},
    "VANDALISM":                {"severity": "MEDIUM",   "departments": ["RPD_NON_EMERGENCY", "SANITATION"]},
    "CAR_BREAK_IN":             {"severity": "HIGH",     "departments": ["RPD_EMERGENCY"]},
    "ZOMBIE_SIGHTING":          {"severity": "CRITICAL", "departments": ["RPD_EMERGENCY", "STARS_UNIT"]},
    "UMBRELLA_CORP_ACTIVITY":   {"severity": "CRITICAL", "departments": ["STARS_UNIT"], "immediateEscalation": True},
}
```

**Key implementation details:**
- All endpoints require `X-Service-Token` header. Validate against `SERVICE_TOKEN` env var.
  Return 401 if missing or invalid — this service is internal only.
- After classifying a report, callback to `reports-service PATCH /v1/reports/:reportId/status`
  with `{"status": "TRIAGED"}`. Use httpx with a short timeout (5s). Log failures but do not
  fail the triage response.
- For batch: sort incoming reports so `ZOMBIE_SIGHTING` and `UMBRELLA_CORP_ACTIVITY` are
  processed first, regardless of order in the request body.
- `UMBRELLA_CORP_ACTIVITY` sets `immediateEscalation: true` on the routing decision.
- W3C tracing: read `traceparent` from incoming request headers and forward on all
  outbound httpx calls to reports-service.

**Environment variables:**
```
PORT                    3002
POSTGRES_HOST
POSTGRES_PORT           5432
POSTGRES_USER
POSTGRES_PASSWORD
POSTGRES_DB_TRIAGE      triage
SERVICE_TOKEN
REPORTS_SERVICE_URL     http://reports-service.rpd311.svc.cluster.local/v1
TRACEPARENT_PROPAGATION_ENABLED  true
```

### 4. `services/status-service/src/`

**Stack:** Go 1.22, `net/http` (stdlib) or `chi` router, `go-redis/redis`, httpx-style
outbound calls via `net/http`.

Implement all endpoints defined in `services/status-service/openapi.yaml`:

| Method | Path | Notes |
|---|---|---|
| `GET` | `/v1/status/:reportId` | Cache-first (30s TTL); miss → fetch from reports + triage |
| `GET` | `/v1/feed` | Paginated public feed (60s TTL); excludes CLOSED and anonymous |
| `GET` | `/v1/stats` | Aggregate stats (5min TTL) |
| `GET` | `/v1/stats/by-type` | Per-type breakdown (5min TTL) |
| `GET` | `/v1/stats/heatmap` | Location heatmap data (10min TTL) |
| `POST` | `/v1/internal/cache/invalidate` | Evict a report from Redis cache |
| `GET` | `/v1/health` | Check Redis + reports-service + triage-service |

**Key implementation details:**
- All responses must include `X-Cache: HIT` or `X-Cache: MISS` and `X-Cache-Age` headers.
- `PublicReportStatus` is a reduced enum — map internal statuses before caching:
  - `SUBMITTED` → `SUBMITTED`
  - `TRIAGED` → `SUBMITTED` (not yet actioned from public perspective)
  - `IN_PROGRESS` → `IN_PROGRESS`
  - `RESOLVED` → `RESOLVED`
  - `ESCALATED` → `ESCALATED`
  - `CLOSED` → exclude from feed entirely
- `/v1/internal/cache/invalidate` requires `X-Service-Token` header. All other
  endpoints are public — no auth required.
- Heatmap: aggregate report locations into ~100m grid cells. A simple approach is
  to round lat/lng to 3 decimal places (~110m precision) and group by the rounded value.
- W3C tracing: read `traceparent` from incoming requests and forward on all outbound
  calls to reports-service and triage-service.
- Redis outage should degrade gracefully — bypass cache and fetch from upstream
  services. Return `status: degraded` on `/v1/health` but still serve responses.

**Environment variables:**
```
PORT                    3003
REDIS_URL               redis://redis:6379
SERVICE_TOKEN
REPORTS_SERVICE_URL     http://reports-service.rpd311.svc.cluster.local/v1
TRIAGE_SERVICE_URL      http://triage-service.rpd311.svc.cluster.local/v1
CACHE_TTL_STATUS_SECONDS    30
CACHE_TTL_FEED_SECONDS      60
CACHE_TTL_STATS_SECONDS     300
CACHE_TTL_HEATMAP_SECONDS   600
TRACEPARENT_PROPAGATION_ENABLED  true
```

---

## Cross-cutting concerns

### W3C traceparent propagation (CRITICAL)

Every service must read the `traceparent` header from incoming requests and forward
it on all outbound HTTP calls. This is what populates the Service Graph in Postman
API Catalog. Without it, triage-service will appear as a disconnected node even
after discovery.

Implement as middleware in each service — do not handle it per-endpoint.

**Node.js example:**
```js
// middleware/tracing.js
export function tracingMiddleware(req, res, next) {
  const traceparent = req.headers['traceparent'];
  if (traceparent) {
    req.outboundHeaders = { traceparent };
  }
  next();
}
// then in any axios/fetch call:
// headers: { ...req.outboundHeaders }
```

**Python example:**
```python
# middleware/tracing.py
from starlette.middleware.base import BaseHTTPMiddleware

class TraceParentMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        traceparent = request.headers.get("traceparent")
        request.state.traceparent = traceparent
        return await call_next(request)
# then in any httpx call:
# headers={"traceparent": request.state.traceparent} if request.state.traceparent else {}
```

**Go example:**
```go
// middleware/tracing.go
func TracingMiddleware(next http.Handler) http.Handler {
    return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
        traceparent := r.Header.Get("traceparent")
        ctx := context.WithValue(r.Context(), "traceparent", traceparent)
        next.ServeHTTP(w, r.WithContext(ctx))
    })
}
// then when making outbound requests:
// req.Header.Set("traceparent", ctx.Value("traceparent").(string))
```

### Service-to-service auth

Internal endpoints use a shared secret passed in the `X-Service-Token` header.
The secret is the `SERVICE_TOKEN` env var, injected from the `rpd311-secrets`
Kubernetes Secret.

Validate on:
- `PATCH /v1/reports/:reportId/status` (reports-service)
- All triage-service endpoints
- `POST /v1/internal/cache/invalidate` (status-service)

### Error response shape

All services must return errors in this shape (defined in each OpenAPI spec):

```json
{
  "error": "VALIDATION_ERROR",
  "message": "The 'type' field is required.",
  "requestId": "uuid-v4",
  "details": []
}
```

Generate a UUID v4 `requestId` for every request (attach to logs too).

### Tone

Error messages and log output should be consistent with the Raccoon City setting —
dry, bureaucratic, and matter-of-fact. A few examples:

```
# Good
"Report submitted. Estimated response time: 3–5 business days."
"UMBRELLA_CORP_ACTIVITY reports are escalated immediately. STARS Unit has been notified."
"triage-service unavailable. Report queued for retry."

# Avoid
"Oops! Something went wrong."
"Error 500: Internal Server Error"
```

This only applies to user-facing messages and log strings — not to enum values,
field names, or HTTP status codes, which must match the OpenAPI specs exactly.

---

## Database schemas

### reports-service (Postgres — database: `reports`)

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE incident_type AS ENUM (
  'POTHOLE', 'DOWNED_TREE', 'NOISE_COMPLAINT', 'SUSPICIOUS_PERSON',
  'VANDALISM', 'CAR_BREAK_IN', 'ZOMBIE_SIGHTING', 'UMBRELLA_CORP_ACTIVITY'
);

CREATE TYPE severity_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');

CREATE TYPE report_status AS ENUM (
  'SUBMITTED', 'TRIAGED', 'IN_PROGRESS', 'RESOLVED', 'CLOSED', 'ESCALATED'
);

CREATE TABLE reports (
  report_id         UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  type              incident_type NOT NULL,
  description       TEXT NOT NULL,
  lat               NUMERIC(9,6) NOT NULL,
  lng               NUMERIC(9,6) NOT NULL,
  address           TEXT,
  severity          severity_level NOT NULL DEFAULT 'MEDIUM',
  status            report_status NOT NULL DEFAULT 'SUBMITTED',
  anonymous         BOOLEAN NOT NULL DEFAULT FALSE,
  reporter_name     TEXT,
  reporter_contact  TEXT,
  triage_reference  UUID,
  resolved_by       TEXT,
  internal_note     TEXT,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at        TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE attachments (
  attachment_id   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  report_id       UUID NOT NULL REFERENCES reports(report_id) ON DELETE CASCADE,
  filename        TEXT NOT NULL,
  mime_type       TEXT NOT NULL,
  size_bytes      INTEGER NOT NULL,
  s3_key          TEXT NOT NULL,
  caption         TEXT,
  uploaded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_reports_type     ON reports(type);
CREATE INDEX idx_reports_status   ON reports(status);
CREATE INDEX idx_reports_severity ON reports(severity);
CREATE INDEX idx_reports_location ON reports(lat, lng);
CREATE INDEX idx_reports_created  ON reports(created_at DESC);
```

### triage-service (Postgres — database: `triage`)

```sql
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TYPE assignment_status AS ENUM (
  'PENDING', 'ACKNOWLEDGED', 'COMPLETED', 'CANCELLED', 'ESCALATED'
);

CREATE TYPE department AS ENUM (
  'PUBLIC_WORKS', 'RPD_NON_EMERGENCY', 'RPD_EMERGENCY', 'SANITATION', 'STARS_UNIT'
);

CREATE TYPE severity_level AS ENUM ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL');

CREATE TABLE assignments (
  assignment_id           UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
  report_id               UUID NOT NULL UNIQUE,
  assigned_severity       severity_level NOT NULL,
  classification_reason   TEXT,
  immediate_escalation    BOOLEAN NOT NULL DEFAULT FALSE,
  status                  assignment_status NOT NULL DEFAULT 'PENDING',
  acknowledged_by         TEXT,
  acknowledged_at         TIMESTAMPTZ,
  triaged_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at              TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE assignment_departments (
  id              SERIAL PRIMARY KEY,
  assignment_id   UUID NOT NULL REFERENCES assignments(assignment_id) ON DELETE CASCADE,
  department      department NOT NULL,
  is_primary      BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE routing_log (
  id              SERIAL PRIMARY KEY,
  assignment_id   UUID NOT NULL REFERENCES assignments(assignment_id),
  event           TEXT NOT NULL,
  detail          TEXT,
  logged_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_assignments_report    ON assignments(report_id);
CREATE INDEX idx_assignments_status    ON assignments(status);
CREATE INDEX idx_assignments_severity  ON assignments(assigned_severity);
CREATE INDEX idx_dept_assignment       ON assignment_departments(assignment_id);
CREATE INDEX idx_dept_department       ON assignment_departments(department);
```

---

## Testing expectations

Each service should have:
- Unit tests for routing/business logic (triage routing table, status mapping, cache TTLs)
- Integration tests for each endpoint against a real Postgres/Redis/LocalStack instance
- A `health` endpoint test that verifies dependency checks work

Use whatever test framework is idiomatic for each stack:
- Node.js: Jest + supertest
- Python: pytest + httpx
- Go: stdlib `testing` + `net/http/httptest`

---

## What NOT to build

- No frontend — this is an API-only demo
- No authentication service — JWT auth is stubbed in the OpenAPI specs but not
  implemented. The `bearerAuth` security scheme is defined but all endpoints should
  treat unauthenticated requests as valid public callers for now. Service-to-service
  auth (`X-Service-Token`) must be implemented.
- No message queue — triage-service is called synchronously via HTTP from reports-service,
  not via Kafka/SQS. Keep it simple.
- No Scorecards or Analytics tab features — these are explicitly out of scope per the
  course outline this app supports. **API Governance / spec linting is in scope**, though:
  the demo intentionally connects the repo's OpenAPI specs and shows their governance
  rule violations (a sub-par spec-quality result) as a teaching moment. Do NOT pre-fix
  the specs to pass linting — the flagged violations are the point. (Spec-linting
  compliance feeds the Scorecard, but the Scorecard tab itself stays out of scope.)

---

## Useful context

- This app supports a Postman internal training course: "Connecting Services to API Catalog"
- Lessons 6 and 7 demo the Postman Insights Agent and Cluster Watcher against this app
  running on a local minikube / kind cluster. Both agents report outbound to Postman's
  cloud, so no public ingress or cloud cluster is required — see `k8s/README.md`.
- `triage-service` having no public ingress is intentional and load-bearing for the demo.
  Do not add an ingress rule for it.
- The Raccoon City setting is a joke. The code should be professional.
