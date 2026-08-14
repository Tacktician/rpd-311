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
│       ├── ci.yaml                         # test → build → minikube E2E gate → EKS deploy
│       └── teardown.yaml                   # manual `terraform destroy` of the prod cluster
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
│   │   └── secret-local.yaml               # K8s Secret for the demo cluster
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
│   ├── dev/
│   │   └── datastores.yaml                 # in-cluster Postgres/Redis/LocalStack
│   ├── prod/                               # the only EKS-specific manifests
│   │   ├── ingress-prod.yaml               # nginx behind an AWS NLB, no host rule
│   │   └── create-secret.sh                # Secret from CI secrets, not placeholders
│   └── ingress/
│       └── ingress-local.yaml              # nginx (minikube / kind)
│
├── infra/
│   └── terraform/                          # EKS prod cluster (VPC, EKS, node group, ECR)
│       └── bootstrap/                      # one-time: tfstate bucket + GitHub OIDC role
│
├── docker-compose.yml                      # base services (Postgres, Redis, LocalStack)
├── docker-compose.local.yml               # local overrides (ports, volumes, hot-reload)
└── README.md
```

---

## Environments

| | Where | What it is |
|---|---|---|
| **Local** | docker-compose | Fastest loop for service code. `docker compose up`, no cluster. |
| **Local cluster** | minikube / kind | Rehearsal for prod. Same images, same manifests, in-cluster datastores. |
| **Prod** | EKS (`rpd311-prod`) | Deployment destination. Provisioned by `infra/terraform/`. |

minikube and EKS run the **same images, the same manifests, and the same in-cluster
Postgres / Redis / LocalStack**. Only two files differ (`k8s/prod/`), which is what makes
the CI gate meaningful: `deploy-prod` will not run until the full E2E suite passes on a
real local cluster.

```
unit tests ──┬── docker-build ─────┐
             ├── integration ──────┤
             └── minikube-e2e ─────┴── deploy-prod  (push to main only)
```

`deploy-prod` self-skips until the AWS repo variables are configured, so CI is green
out of the box with no cloud credentials. See **[infra/terraform/README.md](infra/terraform/README.md)**
for the one-time bootstrap, the cost breakdown (~$0.21/hour), and the teardown workflow.

---

## Prerequisites

- Docker + Docker Compose
- minikube or kind
- kubectl
- Node.js 20+ (reports-service)
- Python 3.12+ (triage-service)
- Go 1.22+ (status-service)
- Terraform 1.10+ and the AWS CLI — only for the EKS prod path

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
kubectl apply -f k8s/dev/datastores.yaml       # in-cluster Postgres/Redis/LocalStack
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
After deploying the app to the minikube / kind cluster, install the Postman Insights
Agent in Discovery Mode. The agent reports outbound to Postman's cloud, so no public
ingress is required. All three services — including `triage-service`, which has no
public URL — will appear in API Catalog.

See `k8s/README.md` for installation steps.

### Cluster Watcher (Lesson 7)
Install the Cluster Watcher CRD to surface deployment metadata (Git commit,
branch, namespace) alongside discovered services.

See `k8s/README.md` for installation steps.

---

## Capstone project

This repo doubles as the project template for the **Level 3 capstone**: build a headless
`golden-path.sh` that programmatically provisions a Postman workspace, catalogs all three
OpenAPI specs, generates and runs collections through staged quality gates, and deploys the
Insights Agent to minikube — illuminating the Dev, Test, and Production tabs of API Catalog
with no manual steps.

**→ [`docs/CAPSTONE.md`](docs/CAPSTONE.md)**

Start with its Prerequisites and Step 0 sections. Step 0 gets the application stack green
before any Postman work begins, which is where most of the debugging time otherwise goes.

Two notes for anyone attempting it:
- **Fork to your personal GitHub account** (not an org — orgs often gate third-party app access).
- Any cloud deploy path in this repo (terraform, a prod deploy CI job) is **out of scope** for
  the capstone. It needs AWS credentials and stays inert without them, so forking costs nothing.

---

## W3C tracing

All three services propagate `traceparent` headers on outbound calls.
This is required for the Service Graph on the API Catalog Overview tab to
show dependency edges between services.

`TRACEPARENT_PROPAGATION_ENABLED=true` is set in `k8s/base/configmap-common.yaml`.
The nginx ingress forwards `traceparent` and `tracestate` from inbound requests, and
each service originates a trace when the inbound request carries none.

---

_RPD 311 is a fictional application for demo purposes.
The City of Raccoon City, the Raccoon Police Department, and the STARS unit
are properties of Capcom. No actual civic services were harmed._
