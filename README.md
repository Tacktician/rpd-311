# RPD 311

**Raccoon City Civic Incident Reporting Platform**
_Demo application for Postman API Catalog — Connecting Services (Lessons 6–7)_

> "Raccoon City is committed to responsive civic services. Please allow 3–5 business
> days for non-emergency incidents. Zombie-related complaints may experience longer
> resolution times due to staffing constraints." — Office of the Mayor

---

## What is this

RPD 311 is a fictional microservice application used to demonstrate Kubernetes
deployment and Postman API Catalog service discovery. Residents of Raccoon City
submit civic incident reports — noise complaints, potholes, car break-ins, zombie
sightings, and suspected Umbrella Corporation activity — via a REST API.

The app exists to show how three services with different traffic profiles, visibility
levels, and infrastructure needs can be deployed to Kubernetes and automatically
discovered by Postman API Catalog using the Insights Agent and Cluster Watcher.

---

## Services

| Service | Stack | Port | Visibility | Description |
|---|---|---|---|---|
| `reports-service` | Node.js / Express | 3001 | Public | Incident submission and management |
| `triage-service` | Python / FastAPI | 3002 | **Internal only** | Classification and department routing |
| `status-service` | Go | 3003 | Public (read-only) | Public status lookup and statistics |

`triage-service` has no public ingress — it is only reachable inside the Kubernetes
cluster. It will not appear in Postman API Catalog until the Insights Agent or
Cluster Watcher discovers it. This is the core demo moment for Lessons 6 and 7.

---

## Repo structure

```
rpd311/
├── .github/
│   └── workflows/
│       ├── ci.yaml                         # lint, test, build, push to ECR
│       └── deploy.yaml                     # kubectl apply on merge to main
│
├── services/
│   ├── reports-service/
│   │   ├── src/                            # Node.js source
│   │   ├── Dockerfile
│   │   ├── package.json
│   │   └── openapi.yaml                    # ← source of truth for this spec
│   ├── triage-service/
│   │   ├── src/                            # Python source
│   │   ├── Dockerfile
│   │   ├── requirements.txt
│   │   └── openapi.yaml
│   └── status-service/
│       ├── src/                            # Go source
│       ├── Dockerfile
│       ├── go.mod
│       └── openapi.yaml
│
├── k8s/
│   ├── base/
│   │   ├── namespace.yaml
│   │   ├── configmap-common.yaml
│   │   ├── secret-local.yaml               # local dev only
│   │   └── external-secret-eso.yaml        # EKS only (ESO + Secrets Manager)
│   ├── reports-service/
│   │   ├── reports-deployment.yaml
│   │   ├── reports-service.yaml
│   │   └── reports-hpa.yaml
│   ├── triage-service/
│   │   ├── triage-deployment.yaml
│   │   └── triage-service.yaml             # ClusterIP only — no ingress
│   ├── status-service/
│   │   ├── status-deployment.yaml
│   │   └── status-service.yaml
│   └── ingress/
│       ├── ingress-local.yaml              # nginx (minikube / kind)
│       └── ingress-eks.yaml               # ALB (EKS)
│
├── docker-compose.yml                      # base services (Postgres, Redis, LocalStack)
├── docker-compose.local.yml               # local overrides (ports, volumes, hot-reload)
└── README.md
```

---

## Prerequisites

### Local development
- Docker + Docker Compose
- minikube or kind
- kubectl
- Node.js 20+ (reports-service)
- Python 3.12+ (triage-service)
- Go 1.22+ (status-service)

### EKS demo environment
- AWS CLI configured
- EKS cluster v1.19+ provisioned
- AWS Load Balancer Controller installed
- External Secrets Operator installed
- ECR repositories created
- Secrets provisioned in AWS Secrets Manager (see `k8s/base/external-secret-eso.yaml`)

---

## Quick start (local)

```bash
# 1. Start dependencies (Postgres, Redis, LocalStack)
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d

# 2. Start the cluster
minikube start --cpus 4 --memory 8192
minikube addons enable ingress
minikube addons enable metrics-server

# 3. Add local DNS
echo "$(minikube ip)  rpd311.local" | sudo tee -a /etc/hosts

# 4. Apply manifests
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/configmap-common.yaml
kubectl apply -f k8s/base/secret-local.yaml    # edit placeholders first
kubectl apply -f k8s/reports-service/
kubectl apply -f k8s/triage-service/
kubectl apply -f k8s/status-service/
kubectl apply -f k8s/ingress/ingress-local.yaml

# 5. Verify
kubectl get pods -n rpd311
curl http://rpd311.local/v1/reports/health
curl http://rpd311.local/v1/status/health

# triage-service — internal only, reach via exec
kubectl run curl-test --image=curlimages/curl -it --rm -n rpd311 -- \
  curl http://triage-service.rpd311.svc.cluster.local/v1/health
```

---

## Incident types

| Type | Severity | Routes to |
|---|---|---|
| `POTHOLE` | LOW | Public Works |
| `DOWNED_TREE` | LOW | Public Works |
| `NOISE_COMPLAINT` | MEDIUM | RPD Non-Emergency |
| `SUSPICIOUS_PERSON` | MEDIUM | RPD Non-Emergency |
| `VANDALISM` | MEDIUM | RPD Non-Emergency + Sanitation |
| `CAR_BREAK_IN` | HIGH | RPD Emergency |
| `ZOMBIE_SIGHTING` | CRITICAL | RPD Emergency + STARS Unit |
| `UMBRELLA_CORP_ACTIVITY` | CRITICAL | STARS Unit (immediate escalation) |

---

## Postman API Catalog

### Code Discovery (Lesson 3)
OpenAPI specs are co-located with each service in `services/<name>/openapi.yaml`.
Point Postman Code Discovery at this repository — it will find all three specs automatically.

### Insights Agent (Lesson 6)
After deploying to EKS, install the Postman Insights Agent in Discovery Mode.
All three services — including `triage-service`, which has no public URL — will
appear in API Catalog.

See `k8s/README.md` for installation steps.

### Cluster Watcher (Lesson 7)
Install the Cluster Watcher CRD to surface deployment metadata (Git commit,
branch, namespace) alongside discovered services.

See `k8s/README.md` for installation steps.

---

## W3C tracing

All three services propagate `traceparent` headers on outbound calls.
This is required for the Service Graph on the API Catalog Overview tab to
show dependency edges between services.

`TRACEPARENT_PROPAGATION_ENABLED=true` is set in `k8s/base/configmap-common.yaml`.
Both ingress configurations forward `traceparent` and `tracestate` from inbound requests.

---

_RPD 311 is a fictional application for demo purposes.
The City of Raccoon City, the Raccoon Police Department, and the STARS unit
are properties of Capcom. No actual civic services were harmed._
