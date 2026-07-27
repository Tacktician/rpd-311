# RPD 311 — Architecture Roadmap
**Demo App for Postman API Catalog: Connecting Services (Lessons 6–7)**
_City of Raccoon City — Civic Incident Reporting Platform_
_Revision: 2026-07-22_

---

## Overview

RPD 311 is a fictional civic incident reporting platform for Raccoon City. Residents submit reports of local incidents — noise complaints, vandalism, car break-ins, potholes, zombie sightings, and suspected Umbrella Corporation activity — via a lightweight frontend. The platform triages reports and routes them to the appropriate city department.

The app exists to demonstrate microservice architecture, Kubernetes deployment, and Postman API Catalog service discovery. It is intentionally deadpan: the OpenAPI specs, Kubernetes manifests, and routing logic treat `ZOMBIE_SIGHTING` with the same dry bureaucratic seriousness as `POTHOLE`.

---

## App concept

> "Raccoon City is committed to responsive civic services. Please allow 3–5 business days for non-emergency incidents. Zombie-related complaints may experience longer resolution times due to staffing constraints."

**Incident types (enum):**

| Code | Description | Routes to |
|---|---|---|
| `POTHOLE` | Road surface damage | Public Works |
| `NOISE_COMPLAINT` | Excessive noise from neighbors or undead | RPD Non-Emergency |
| `VANDALISM` | Graffiti, property damage | RPD Non-Emergency + Sanitation |
| `CAR_BREAK_IN` | Vehicle break-in or theft | RPD Emergency |
| `ZOMBIE_SIGHTING` | Confirmed or suspected undead activity | RPD Emergency + STARS Unit |
| `UMBRELLA_CORP_ACTIVITY` | Suspicious Umbrella Corporation presence | STARS Unit (escalate immediately) |
| `DOWNED_TREE` | Fallen tree or debris | Public Works |
| `SUSPICIOUS_PERSON` | Unidentified individual acting erratically | RPD Non-Emergency (may escalate) |

---

## Services (3)

### 1. `reports-service`

The primary public-facing API. Residents submit incident reports with a type, description, location (lat/lng), optional photo URL, and reporter contact info. Handles CRUD for all reports.

- **Stack:** Node.js / Express
- **Database:** Postgres (`reports`, `attachments` tables)
- **Storage:** S3 (`rpd311-attachments` bucket) for photo uploads
- **Auth:** JWT validation against `auth-service` on write endpoints; public read on `GET /reports/{id}` (transparency)
- **OpenAPI spec:** `reports-service/openapi.yaml`
- **Key endpoints:**

| Method | Path | Description |
|---|---|---|
| `POST` | `/reports` | Submit a new incident report |
| `GET` | `/reports/{id}` | Retrieve a single report (public) |
| `GET` | `/reports` | List reports (filterable by type, status, location radius) |
| `PATCH` | `/reports/{id}/status` | Update report status (internal only) |
| `POST` | `/reports/{id}/attachments` | Upload a photo attachment |
| `GET` | `/health` | Health check |

---

### 2. `triage-service`

An internal-only worker service. No public endpoints. Consumes new report events from `reports-service` (via HTTP webhook or polling), classifies reports by severity, applies routing logic, and dispatches to the appropriate department queue. This service has no frontend exposure — it is only discoverable via the Postman Insights Agent or Cluster Watcher, making it a perfect demo subject for why service discovery matters.

- **Stack:** Python / FastAPI
- **Database:** Postgres (`assignments`, `routing_log` tables)
- **Auth:** Internal service-to-service only (shared secret header); no public JWT auth
- **OpenAPI spec:** `triage-service/openapi.yaml`
- **Key endpoints:**

| Method | Path | Description |
|---|---|---|
| `POST` | `/triage` | Receive and classify a report from reports-service |
| `GET` | `/assignments/{reportId}` | Get routing decision for a report |
| `GET` | `/queue/{department}` | List pending assignments for a department |
| `GET` | `/health` | Health check |

**Routing logic (demo-friendly pseudocode):**

```
if type == ZOMBIE_SIGHTING or UMBRELLA_CORP_ACTIVITY:
    severity = CRITICAL
    route → RPD Emergency + STARS Unit
elif type == CAR_BREAK_IN:
    severity = HIGH
    route → RPD Emergency
elif type == VANDALISM or NOISE_COMPLAINT or SUSPICIOUS_PERSON:
    severity = MEDIUM
    route → RPD Non-Emergency
    if VANDALISM: also route → Sanitation
elif type == POTHOLE or DOWNED_TREE:
    severity = LOW
    route → Public Works
```

---

### 3. `status-service`

A public-facing read API that exposes report status and city-wide incident statistics to residents. Intentionally separate from `reports-service` — it is read-only, has different caching and rate-limit needs, and is the only service the city's public dashboard calls. Calls `reports-service` and `triage-service` internally to aggregate data.

- **Stack:** Go (fast, low-memory, good for a read-heavy cache layer)
- **Database:** Redis (cache layer only; source of truth lives in reports-service Postgres)
- **Auth:** Public read — no auth required
- **OpenAPI spec:** `status-service/openapi.yaml`
- **Key endpoints:**

| Method | Path | Description |
|---|---|---|
| `GET` | `/status/{reportId}` | Public status lookup for a submitted report |
| `GET` | `/stats` | City-wide incident stats (counts by type, avg resolution time) |
| `GET` | `/feed` | Recent public incidents (paginated, excludes sensitive fields) |
| `GET` | `/health` | Health check |

---

## Repo structure

```
rpd311/
├── reports-service/
│   ├── src/
│   ├── Dockerfile
│   ├── openapi.yaml
│   └── k8s/
│       ├── namespace.yaml
│       ├── deployment.yaml
│       ├── service.yaml
│       └── secret.yaml
├── triage-service/
│   ├── src/
│   ├── Dockerfile
│   ├── openapi.yaml
│   └── k8s/
│       ├── deployment.yaml
│       ├── service.yaml
│       └── secret.yaml
├── status-service/
│   ├── src/
│   ├── Dockerfile
│   ├── openapi.yaml
│   └── k8s/
│       ├── deployment.yaml
│       ├── service.yaml
│       └── configmap.yaml
├── k8s/dev/
│   └── datastores.yaml       ← In-cluster Postgres + Redis + LocalStack (S3) for minikube
├── docker-compose.yml        ← Local dev (LocalStack for S3, Postgres + Redis containers)
├── .github/
│   └── workflows/
│       └── ci.yaml           ← Lint, test, build images, integration tests
└── README.md
```

---

## W3C tracing (required for Service Graph)

All three services must propagate `traceparent` headers on every outbound HTTP call. This is what populates the Service Graph on the Overview tab in Postman API Catalog.

Implementation per stack:

- **Node.js (reports-service):** middleware reads `traceparent` from `req.headers`, forwards it via `axios` default headers
- **Python (triage-service):** FastAPI middleware reads and forwards `traceparent` via `httpx` headers
- **Go (status-service):** `net/http` middleware reads and forwards `traceparent`

No full distributed tracing stack (Jaeger, Zipkin) required for the demo — just header propagation.

---

## Infrastructure: local minikube / kind

The app runs entirely on a local Kubernetes cluster — no cloud provider is required.
This keeps the demo cloud-agnostic and focused on Postman API Catalog rather than any
one deployment target.

| Component | Local equivalent |
|---|---|
| Postgres (reports, triage) | `postgres:15` container / in-cluster (`k8s/dev/datastores.yaml`) |
| Redis (status cache) | `redis:7` container / in-cluster |
| S3 (attachments) | LocalStack `s3` |
| K8s | `minikube` or `kind` |
| Ingress | nginx ingress controller (minikube addon) |
| Container images | built locally, loaded with `minikube image load` (no registry) |

No AWS credentials are needed. `docker-compose up` brings all dependencies online for
service development; `k8s/dev/datastores.yaml` provides the same datastores in-cluster
for a full minikube run.

Lessons 6 and 7 (Insights Agent, Cluster Watcher) run against this local cluster —
both agents report **outbound** to Postman's cloud, so no public ingress or managed
cloud cluster is required.

---

## Postman API Catalog integration

### What gets discovered

| Service | Discovery method (Lesson) | Notes |
|---|---|---|
| `reports-service` | Insights Agent (L6) + Cluster Watcher (L7) | Public-facing; has external traffic |
| `triage-service` | Insights Agent (L6) + Cluster Watcher (L7) | **Internal only** — no public endpoints; best demo of why discovery matters |
| `status-service` | Insights Agent (L6) + Cluster Watcher (L7) | Read-only public; different traffic profile |

### Kubernetes labels (required for catalog metadata)

All three `Deployment` manifests should include these labels so Postman can surface rich metadata:

```yaml
labels:
  app: reports-service           # or triage-service / status-service
  version: "1.0.0"
  team: civic-platform
  environment: demo
  postman.com/service-name: reports-service
```

### Namespace

All three services deploy into a single namespace: `rpd311`. Keeps the demo cluster tidy and scopes the Insights Agent discovery cleanly.

```bash
kubectl create namespace rpd311
```

---

## Build phases

| Phase | Work | Environment | Lesson dependency |
|---|---|---|---|
| **1 — Specs** | Write all three OpenAPI specs; define incident type enum | None | Lessons 2–4 (Code Discovery demo) |
| **2 — Auth scaffold** | Decide JWT strategy (shared lib vs. per-service validation); wire up Postgres connection | Local | — |
| **3 — reports-service** | Implement all endpoints; LocalStack S3 upload; traceparent middleware | Local | — |
| **4 — triage-service** | Implement routing logic; wire to reports-service webhook; Postgres assignments table | Local | — |
| **5 — status-service** | Implement read endpoints; Redis cache layer; aggregate from reports + triage | Local | — |
| **6 — K8s local** | Write all manifests; deploy to minikube; verify service-to-service calls work in cluster | minikube / kind | — |
| **7 — CI pipeline** | GitHub Actions: lint → test → build images → integration tests | GitHub | — |
| **8 — Insights Agent (L6)** | Install the Insights Agent in the cluster; drive traffic; verify discovery of all three services (incl. triage) | minikube / kind | Lesson 6 |
| **9 — Cluster Watcher (L7)** | Install the Cluster Watcher; verify deployment metadata (commit/branch/namespace) | minikube / kind | Lesson 7 |
| **10 — Demo recording** | Record Insights Agent (L6) and Cluster Watcher (L7) walkthroughs | minikube / kind | Lessons 6–7 |

---

## Blockers

**Discovery-demo manifests (Phases 8–10):** The Insights Agent DaemonSet and Cluster
Watcher CRD/controller manifests are not yet in the repo (the Lesson 6/7 sections in
`k8s/README.md` reference them as placeholders). These need to be added and validated
against the minikube cluster before demo recording. The agents require a `POSTMAN_API_KEY`.

**triage-service routing confirmation:** The routing logic above is draft. Confirm department queue names and escalation rules with the course author before finalizing the OpenAPI spec — the enum values and routing table appear in lesson prose.

**S3 bucket policy for attachments:** Confirm whether `GET /reports/{id}` attachment URLs should be public pre-signed URLs or require auth. Affects the `reports-service` OpenAPI spec and the lesson 3 Code Discovery demo.

---

## What's next

1. **OpenAPI specs** — draft all three specs (incident type enum is the fun part)
2. **K8s manifests** — `Deployment`, `Service`, `ConfigMap`, `Secret` for each service in the `rpd311` namespace
3. **`docker-compose.yml`** — local dev environment with all dependencies
4. **CI pipeline** — GitHub Actions workflow for lint, test, image build, and integration tests

---

_RPD 311 is a fictional application. The City of Raccoon City, the Raccoon Police Department, and the STARS unit are properties of Capcom. No actual civic services were harmed in the making of this demo._
