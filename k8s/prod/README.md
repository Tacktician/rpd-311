# k8s/prod — EKS-only manifests

Everything under `k8s/base/`, `k8s/dev/`, `k8s/reports-service/`, `k8s/triage-service/`,
and `k8s/status-service/` is shared between minikube and EKS. Only two things differ,
and they live here.

| File | Why prod needs its own |
|---|---|
| `ingress-prod.yaml` | No `host:` rule, so the NLB's generated DNS name works without a domain or ACM certificate. No `configuration-snippet`, which modern ingress-nginx blocks by default and which was never load-bearing (nginx forwards `traceparent` anyway). |
| `create-secret.sh` | `k8s/base/secret-local.yaml` ships a committed `changeme-service-token`. Prod builds the Secret from repository secrets and refuses to run if `SERVICE_TOKEN` is unset or still the placeholder. |

Keeping this set as small as possible is the point. Every file here is a place where a
green `minikube-e2e` run can still fail on EKS, so the shorter the list, the more the
CI gate is worth.

The datastore hosts in `create-secret.sh` are the in-cluster ones from
`k8s/dev/datastores.yaml` — prod runs the same Postgres, Redis, and LocalStack
containers as the local cluster. Swapping in RDS and ElastiCache means changing
`POSTGRES_HOST` and `REDIS_URL` there and nothing else.

`triage-service` has **no** ingress rule here, same as locally. That is load-bearing for
Lessons 6 and 7: it stays invisible to Postman API Catalog until the Insights Agent or
Cluster Watcher discovers it.

## Applying by hand

The `deploy-prod` job does all of this — see `infra/terraform/README.md`. To do it
manually against an existing cluster:

```bash
aws eks update-kubeconfig --name rpd311-prod --region us-east-1

kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/configmap-common.yaml
SERVICE_TOKEN="$(openssl rand -hex 32)" ./k8s/prod/create-secret.sh
kubectl apply -f k8s/dev/datastores.yaml
kubectl apply -f k8s/reports-service/ -f k8s/triage-service/ -f k8s/status-service/
kubectl apply -f k8s/prod/ingress-prod.yaml
```

The ingress controller must already be installed (the deploy job applies the pinned
upstream ingress-nginx AWS manifest, which provisions the NLB).

Note that the Deployments pin `rpd311/<svc>:1.0.0` for the minikube path; on EKS the
deploy job repoints them at the ECR SHA tag with `kubectl set image`. Applying the
manifests by hand leaves them pointing at an image that does not exist in ECR.
