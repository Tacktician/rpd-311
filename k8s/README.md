# RPD 311 — Kubernetes Manifests

Kubernetes manifests for the RPD 311 demo application.
Three services, one namespace (`rpd311`), two environments (local + EKS).

---

## Directory structure

```
rpd311-k8s/
├── base/
│   ├── namespace.yaml              — rpd311 namespace
│   ├── configmap-common.yaml       — shared env vars (service URLs, tracing config)
│   ├── secret-local.yaml           — K8s Secret for local dev (base64 placeholders)
│   └── external-secret-eso.yaml    — ESO ExternalSecret + SecretStore for EKS
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
└── ingress/
    ├── ingress-local.yaml          — nginx ingress for minikube / kind
    └── ingress-eks.yaml            — AWS Load Balancer Controller (ALB) for EKS
```

---

## Local development (minikube / kind)

### Prerequisites
- minikube or kind installed
- kubectl configured
- metrics-server enabled (for HPA)

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

### 2. Add /etc/hosts entry

```bash
# minikube
echo "$(minikube ip)  rpd311.local" | sudo tee -a /etc/hosts

# kind
echo "127.0.0.1  rpd311.local" | sudo tee -a /etc/hosts
```

### 3. Apply manifests

```bash
# Base (namespace, configmap, secrets)
kubectl apply -f base/namespace.yaml
kubectl apply -f base/configmap-common.yaml

# Edit base/secret-local.yaml — replace base64 placeholder values
# then apply:
kubectl apply -f base/secret-local.yaml

# Services
kubectl apply -f reports-service/
kubectl apply -f triage-service/
kubectl apply -f status-service/

# Ingress
kubectl apply -f ingress/ingress-local.yaml
```

### 4. Verify

```bash
kubectl get pods -n rpd311
kubectl get svc -n rpd311
kubectl get ingress -n rpd311

# Health checks
curl http://rpd311.local/v1/reports/health  # → reports-service
curl http://rpd311.local/v1/status/health   # → status-service

# triage-service is only reachable inside the cluster
kubectl run curl-test --image=curlimages/curl -it --rm -n rpd311 -- \
  curl http://triage-service.rpd311.svc.cluster.local/v1/health
```

---

## EKS deployment

### Prerequisites
- EKS cluster v1.19+ provisioned and kubectl configured
- AWS Load Balancer Controller installed
- External Secrets Operator installed
- ACM certificate issued for your demo domain
- Secrets created in AWS Secrets Manager (see `base/external-secret-eso.yaml`)
- ECR repositories created and images pushed

### 1. Update TODOs

Before applying, update the following placeholders:

| File | Field | Replace with |
|---|---|---|
| `base/external-secret-eso.yaml` | `ACCOUNT_ID` | Your AWS account ID |
| `base/external-secret-eso.yaml` | IRSA role ARN | Your ESO IRSA role ARN |
| `ingress/ingress-eks.yaml` | `ACCOUNT_ID`, `CERTIFICATE_ID` | Your ACM cert ARN |
| `ingress/ingress-eks.yaml` | `api.rpd311.raccoon.gov` | Your demo domain |
| All `deployment.yaml` files | `image:` | Your ECR image URIs |

### 2. Apply manifests

```bash
# Base
kubectl apply -f base/namespace.yaml
kubectl apply -f base/configmap-common.yaml
kubectl apply -f base/external-secret-eso.yaml   # ESO syncs secrets from Secrets Manager

# Wait for ESO to sync the secret
kubectl get secret rpd311-secrets -n rpd311

# Services
kubectl apply -f reports-service/
kubectl apply -f triage-service/
kubectl apply -f status-service/

# Ingress (ALB — takes ~2 minutes to provision)
kubectl apply -f ingress/ingress-eks.yaml
kubectl get ingress -n rpd311 --watch
```

### 3. Verify

```bash
kubectl get pods -n rpd311
kubectl get hpa -n rpd311

# ALB hostname (after ingress provisioned)
kubectl get ingress rpd311-ingress-eks -n rpd311 -o jsonpath='{.status.loadBalancer.ingress[0].hostname}'

# Health checks (replace with your domain)
curl https://api.rpd311.raccoon.gov/v1/reports/health
curl https://api.rpd311.raccoon.gov/v1/status/health
```

---

## Postman Insights Agent (Lesson 6)

After EKS deployment, install the Insights Agent in Discovery Mode:

```bash
# Create namespace and secret
kubectl create namespace postman-insights-namespace
kubectl create secret generic postman-agent-secrets \
  --from-literal=POSTMAN_API_KEY=$(kubectl get secret rpd311-secrets -n rpd311 \
    -o jsonpath='{.data.POSTMAN_API_KEY}' | base64 -d) \
  -n postman-insights-namespace

# Apply DaemonSet (see Lesson 6 for manifest and flag details)
# kubectl apply -f postman-insights-agent-daemonset.yaml
```

After discovery, all three services — including `triage-service` (ClusterIP only,
no public URL) — will appear in Postman API Catalog.

---

## Cluster Watcher (Lesson 7)

After EKS deployment, install the Cluster Watcher CRD:

```bash
# See Lesson 7 for CRD installation command and source
# kubectl apply -f cluster-watcher-crd.yaml
```

Navigate to Home > API Catalog > Service Discovery to confirm all three
deployments appear with Git commit, branch, and namespace metadata.

---

## Service visibility summary

| Service | K8s Service type | Ingress rule | Discoverable without agent? |
|---|---|---|---|
| reports-service | ClusterIP | Yes (public) | Yes — via ALB |
| status-service | ClusterIP | Yes (public) | Yes — via ALB |
| triage-service | ClusterIP | **No** | **No — agent required** |

`triage-service` is the demo's key teaching moment: a real, running service
that is completely invisible to API Catalog until the Insights Agent or
Cluster Watcher discovers it.

---

## W3C tracing

All three services must propagate `traceparent` headers on outbound calls.
`TRACEPARENT_PROPAGATION_ENABLED=true` is set in `configmap-common.yaml`.
The nginx and ALB ingress configs are both set to forward `traceparent` and
`tracestate` headers from inbound requests.

Without `traceparent` propagation, `triage-service` will appear in the catalog
after discovery but the Service Graph on the Overview tab will not show
dependency edges between services.
