# e2e/ — cross-service integration tests + demo traffic generator

One HTTP harness, two jobs:

- **`test_flow.py`** — integration tests that drive the real reports→triage→status
  flow against live services and their real dependencies (Postgres/Redis/LocalStack).
  They cover the seams unit tests can't: the reports→triage payload contract, the
  severity override + immediate escalation, public status mapping, the status cache,
  triage's internal-only auth, and S3 attachments.
- **`generate_traffic.py`** — the same flows on a loop, to feed the Postman Insights
  Agent a rich, connected Service Graph (including edges into internal triage-service).

Both talk to the services over HTTP and read config from the environment (defaults
match `docker-compose.local.yml`):

| Var | Default |
|---|---|
| `REPORTS_URL` | `http://localhost:3001/v1` |
| `TRIAGE_URL`  | `http://localhost:3002/v1` |
| `STATUS_URL`  | `http://localhost:3003/v1` |
| `SERVICE_TOKEN` | `changeme-service-token` |

## Run the integration tests

```bash
# 1. bring the stack up
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build

# 2. run the suite (from repo root)
pip install -r e2e/requirements.txt
cd e2e && pytest -q
```

CI runs exactly this in the `integration` job (see `.github/workflows/ci.yaml`).

## Generate demo traffic

```bash
cd e2e && pip install -r requirements.txt
python generate_traffic.py            # forever, ~2s apart
python generate_traffic.py -n 50 -d 1 # 50 reports, 1s apart
```

Point it at any environment (local docker compose, or minikube via port-forward) by setting the
`*_URL` vars. Requests are sent without a `traceparent` on purpose — the services
originate one, which is what the Service Graph is built from.
