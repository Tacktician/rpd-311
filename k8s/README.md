# RPD 311 — Kubernetes Manifests

Kubernetes manifests for the RPD 311 demo application.
Three services, one namespace (`rpd311`), on two clusters:

- **minikube / kind** — local testing. Everything below applies here.
- **EKS (`rpd311-prod`)** — the deploy destination, provisioned by
  [`infra/terraform/`](../infra/terraform/README.md) and rolled out by the `deploy-prod`
  CI job on a merge to `main`.

Both clusters run the same images, the same Deployments, Services, ConfigMap, HPA, and
the same in-cluster datastores from `dev/datastores.yaml`. Only `prod/` differs — see
[`prod/README.md`](prod/README.md) for the two files and why each exists. Keeping that
list short is deliberate: `deploy-prod` is gated on the E2E suite passing here first, and
every prod-only file is a place where a green local run can still break the deploy.

---

## Directory structure

```
rpd311-k8s/
├── base/
│   ├── namespace.yaml              — rpd311 namespace
│   ├── configmap-common.yaml       — shared env vars (service URLs, tracing config)
│   └── secret-local.yaml           — K8s Secret for the demo cluster (base64 placeholders)
├── dev/
│   └── datastores.yaml             — in-cluster Postgres, Redis, LocalStack (S3)
├── reports-service/
│   ├── reports-deployment.yaml     — 2 replicas, rolling update, security context
│   ├── reports-service.yaml        — ClusterIP (ingress handles external access)
│   └── reports-hpa.yaml            — HPA: scales 2–6 replicas on CPU/memory
├── triage-service/
│   ├── triage-deployment.yaml      — 1 replica, ClusterIP only, internal visibility
│   └── triage-service.yaml         — ClusterIP only — NO ingress rule (intentional)
├── status-service/
│   ├── status-deployment.yaml      — 2 replicas, lighter resource profile
│   └── status-service.yaml         — ClusterIP (ingress handles external access)
├── ingress/
│   └── ingress-local.yaml          — nginx ingress for minikube / kind
└── prod/                           — EKS-only; everything above is shared
    ├── ingress-prod.yaml           — nginx behind an AWS NLB, no host rule
    └── create-secret.sh            — Secret from CI secrets (no committed placeholders)
```

---

## Deploying to minikube / kind

### Prerequisites
- minikube or kind installed
- kubectl configured
- metrics-server enabled (for HPA)
- The three service images built and loaded into the cluster (see below)

### 1. Start the cluster

```bash
# minikube
minikube start --cpus 4 --memory 8192
minikube addons enable ingress
minikube addons enable metrics-server

# kind (alternative)
kind create cluster --name rpd311
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/main/deploy/static/provider/kind/deploy.yaml
```

### 2. Build and load the service images

Deployments use `imagePullPolicy: IfNotPresent` with local tags (`rpd311/<svc>:1.0.0`),
so the images must exist in the cluster's node — there is no registry.

```bash
for svc in reports-service triage-service status-service; do
  docker build -t "rpd311/$svc:1.0.0" "services/$svc"
  minikube image load "rpd311/$svc:1.0.0"   # kind: kind load docker-image "rpd311/$svc:1.0.0" --name rpd311
done
```

### 3. Add /etc/hosts entry

```bash
# minikube
echo "$(minikube ip)  rpd311.local" | sudo tee -a /etc/hosts

# kind
echo "127.0.0.1  rpd311.local" | sudo tee -a /etc/hosts
```

### 4. Apply manifests

```bash
# Base (namespace, configmap, secret)
kubectl apply -f base/namespace.yaml
kubectl apply -f base/configmap-common.yaml

# Edit base/secret-local.yaml — replace base64 placeholder values
# then apply:
kubectl apply -f base/secret-local.yaml

# In-cluster datastores (Postgres, Redis, LocalStack)
kubectl apply -f dev/datastores.yaml

# Services
kubectl apply -f reports-service/
kubectl apply -f triage-service/
kubectl apply -f status-service/

# Ingress
kubectl apply -f ingress/ingress-local.yaml
```

### 5. Verify

```bash
kubectl get pods -n rpd311
kubectl get svc -n rpd311
kubectl get ingress -n rpd311

# On the macOS docker driver the ingress isn't directly routable — port-forward it:
kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 18080:80 &

# Health checks (Host header selects the ingress rule)
curl -H 'Host: rpd311.local' http://localhost:18080/v1/reports/health  # → reports-service
curl -H 'Host: rpd311.local' http://localhost:18080/v1/status/health   # → status-service

# triage-service is only reachable inside the cluster
kubectl run curl-test --image=curlimages/curl -it --rm -n rpd311 -- \
  curl http://triage-service.rpd311.svc.cluster.local/v1/health
```

The `minikube-e2e` CI job runs exactly this bring-up on every push and PR, then drives
the full `e2e/` suite against it and asserts the ingress routes — including that
`/v1/triage` returns 404 through the ingress. If that job is green, this recipe works.

---

## Deploying to EKS (prod)

Merging to `main` does it: `deploy-prod` runs `terraform apply`, pushes the three images
to ECR tagged with the commit SHA, installs ingress-nginx (which provisions the NLB),
applies base → secret → datastores → services → `prod/ingress-prod.yaml`, repoints the
Deployments at the ECR tags, and re-runs the E2E suite against the live cluster.

Full setup, cost breakdown, and troubleshooting:
**[`infra/terraform/README.md`](../infra/terraform/README.md)**.

Two things worth knowing before you go looking for them:

- **The cluster does not always exist.** The **Teardown (prod)** workflow destroys it to
  stop the ~$0.21/hour meter between demos. The next merge to `main` rebuilds it, which
  takes 15–20 minutes for the control plane and node group.
- **Prod has no domain.** `prod/ingress-prod.yaml` omits `host:`, so the NLB's generated
  DNS name serves everything: `curl http://<nlb-dns-name>/v1/feed`. No ACM, no Route 53.

---

## Postman Insights Agent (Lesson 6)

Once the app is running in the cluster, install the Insights Agent in Discovery Mode.
The agent observes traffic in-cluster and reports **outbound** to Postman's cloud, so
it works on minikube / kind without any public ingress.

```bash
# Create namespace and provide your Postman API key
kubectl create namespace postman-insights-namespace
kubectl create secret generic postman-agent-secrets \
  --from-literal=POSTMAN_API_KEY=<your-postman-api-key> \
  -n postman-insights-namespace

# Apply the Insights Agent DaemonSet (see Lesson 6 for the manifest and flag details)
# kubectl apply -f postman-insights-agent-daemonset.yaml
```

Drive traffic through the flow (e.g. `e2e/generate_traffic.py`) so the agent has calls
to observe. After discovery, all three services — including `triage-service` (ClusterIP
only, no public URL) — will appear in Postman API Catalog.

---

## Cluster Watcher (Lesson 7)

Install the Cluster Watcher to surface deployment metadata. Like the Insights Agent it
reads the cluster and reports outbound, so it runs on minikube / kind.

```bash
# See Lesson 7 for the CRD / controller installation command and source
# kubectl apply -f cluster-watcher-crd.yaml
```

Navigate to Home > API Catalog > Service Discovery to confirm all three
deployments appear with Git commit, branch, and namespace metadata.

---

## Service visibility summary

| Service | K8s Service type | Ingress rule | Discoverable without agent? |
|---|---|---|---|
| reports-service | ClusterIP | Yes (public) | Yes — via ingress |
| status-service | ClusterIP | Yes (public) | Yes — via ingress |
| triage-service | ClusterIP | **No** | **No — agent required** |

`triage-service` is the demo's key teaching moment: a real, running service
that is completely invisible to API Catalog until the Insights Agent or
Cluster Watcher discovers it.

---

## W3C tracing

All three services must propagate `traceparent` headers on outbound calls.
`TRACEPARENT_PROPAGATION_ENABLED=true` is set in `configmap-common.yaml`.
The nginx ingress forwards `traceparent` and `tracestate` headers from inbound
requests, and each service originates a trace when the inbound request has none.

Without `traceparent` propagation, `triage-service` will appear in the catalog
after discovery but the Service Graph on the Overview tab will not show
dependency edges between services.
