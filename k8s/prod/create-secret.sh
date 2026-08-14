#!/usr/bin/env bash
# create-secret.sh — build the rpd311-secrets Secret for the EKS cluster.
#
# Prod does NOT apply k8s/base/secret-local.yaml. That file ships a committed
# "changeme-service-token", and the X-Service-Token shared secret is the only thing
# standing between the internet and triage-service's internal endpoints. Here the
# sensitive values come from the environment (GitHub Actions secrets) and the script
# refuses to run without them.
#
# The datastore hosts are the in-cluster ones from k8s/dev/datastores.yaml — prod runs
# the same Postgres/Redis/LocalStack containers as the local cluster. Swapping in RDS
# and ElastiCache is a matter of changing POSTGRES_HOST and REDIS_URL below.
#
# Usage:
#   SERVICE_TOKEN=... [POSTMAN_API_KEY=...] k8s/prod/create-secret.sh
#
set -euo pipefail

NAMESPACE="${NAMESPACE:-rpd311}"

if [ -z "${SERVICE_TOKEN:-}" ]; then
  echo "SERVICE_TOKEN is not set. Refusing to deploy prod with an unset service token." >&2
  echo "Set it as a repository secret, or export it before running this script." >&2
  exit 1
fi

if [ "${SERVICE_TOKEN}" = "changeme-service-token" ]; then
  echo "SERVICE_TOKEN is still the committed placeholder. Generate a real one:" >&2
  echo "  openssl rand -hex 32" >&2
  exit 1
fi

# Optional — only the Insights Agent (Lesson 6) reads it. Empty is fine otherwise.
POSTMAN_API_KEY="${POSTMAN_API_KEY:-}"

# `create --dry-run | apply` makes this idempotent: it creates the Secret on a fresh
# cluster and updates it in place on redeploys, without a delete/recreate gap that
# would leave pods restarting into a missing Secret.
kubectl create secret generic rpd311-secrets \
  --namespace "$NAMESPACE" \
  --from-literal=POSTGRES_HOST=postgres \
  --from-literal=POSTGRES_PORT=5432 \
  --from-literal=POSTGRES_USER=rpd311 \
  --from-literal=POSTGRES_PASSWORD=changeme \
  --from-literal=POSTGRES_DB_REPORTS=reports \
  --from-literal=POSTGRES_DB_TRIAGE=triage \
  --from-literal=POSTGRES_DB_STATUS=status \
  --from-literal=REDIS_URL=redis://redis:6379 \
  --from-literal=S3_BUCKET_NAME=rpd311-attachments \
  --from-literal=S3_REGION=us-east-1 \
  --from-literal=AWS_ACCESS_KEY_ID=test \
  --from-literal=AWS_SECRET_ACCESS_KEY=test \
  --from-literal=S3_ENDPOINT_URL=http://localstack:4566 \
  --from-literal=SERVICE_TOKEN="$SERVICE_TOKEN" \
  --from-literal=POSTMAN_API_KEY="$POSTMAN_API_KEY" \
  --dry-run=client -o yaml \
  | kubectl apply -f -

# Match the labelling convention the rest of the manifests use.
kubectl label secret rpd311-secrets --namespace "$NAMESPACE" --overwrite \
  app.kubernetes.io/part-of=rpd311 environment=prod >/dev/null

echo "RPD 311: rpd311-secrets provisioned in namespace ${NAMESPACE}."
