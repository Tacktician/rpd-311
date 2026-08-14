# 👑 Level 3 Capstone Project: Headless Golden Path for RPD 311 (Complete Edition)

## 📝 Project Overview

You are the Lead Platform Engineer at the Raccoon City Civic Tech Division. Your mission is to eliminate all manual developer overhead by creating a completely headless "Golden Path" automation script (`golden-path.sh`).

Whenever a project team initializes a new feature branch or service, your script must programmatically construct the entire Postman infrastructure from scratch, deploy the microservices locally to minikube, execute targeted quality gates, and illuminate all three tabs (Dev, Test, Production) of the Postman API Catalog completely hands-off.

**Estimated effort:** 8–15 hours, assuming the prerequisites below are already in place. Budget a full session for prerequisites alone the first time.

**Scope:** minikube only. If your copy of this repo contains a cloud deploy path — terraform under `infra/`, a prod deploy CI job, a teardown workflow — **all of it is out of scope.** It requires AWS credentials you are not expected to have and stays inert without them, so forking costs you nothing and you can ignore it entirely. Note the terminology collision: "Production tab" below means the Postman API Catalog tab, *not* a cloud environment.

---

## 📋 Prerequisites

Work through this list before writing a line of `golden-path.sh`. Every item here has bitten someone.

### Accounts and access

- [ ] **Fork this repository to your personal GitHub account.**
  - A fork is correct — you need write access, which you have on your own fork and not on the upstream. Git history is fine to keep; there is no need for a "clean" copy.
  - **Fork to a personal account, not an organization.** Orgs frequently restrict third-party OAuth apps and GitHub App installs, which means an org admin has to approve before Postman can connect to the repo.
- [ ] **A Postman Enterprise account** on a team where you hold permissions to:
  - create **Service Accounts** and generate service account keys (typically Team Admin)
  - create **team workspaces** (not just personal ones)
  - write to the **API Catalog** (add API definitions, link collections)
  - manage **API Governance** rules and functions, if your instructor includes the governance extension
  - If you are not a Team Admin, get these granted before you start — Step 1 is unbuildable without service account creation.

> ⚠️ **Verify as you go — Step 1:** Confirm your team tier actually exposes Service Accounts and that you can generate a key. Note the exact token-exchange endpoint and the real token TTL from the current Postman docs; this guide assumes ~15 minutes, which materially affects Step 6 (see the callout there).

### Local tooling

| Tool | Version | Notes |
|---|---|---|
| Docker | current | Docker Desktop on macOS/Windows |
| minikube | current | `kind` also works but every command below assumes minikube |
| kubectl | 1.28+ | |
| Postman CLI | current | `postman --version` |
| `jq` | 1.6+ | You will be parsing a lot of JSON in bash |
| `curl` | any | |
| Python | 3.12 | For the repo's `e2e/` harness |
| Bash | **4.0+** | ⚠️ **macOS ships bash 3.2.** If you use associative arrays (`declare -A`) or `${var,,}`, your script breaks on the default shell. Either `brew install bash` and use `#!/usr/bin/env bash`, or stay POSIX-compatible. |

### Cluster resources

- [ ] minikube started with enough headroom. The stack is three services (5 pods with the HPA at baseline), three datastores, and the ingress controller:
  ```bash
  minikube start --cpus 4 --memory 8192
  minikube addons enable ingress
  minikube addons enable metrics-server   # required by reports-service's HPA
  ```
- [ ] `/etc/hosts` entry for the ingress host:
  ```bash
  echo "$(minikube ip)  rpd311.local" | sudo tee -a /etc/hosts
  ```

> ⚠️ **Verify as you go — platform reachability:** On **macOS with the docker driver, `http://rpd311.local` is not directly routable** — the ingress IP lives inside the Docker Desktop VM. Test it with `curl -H 'Host: rpd311.local' http://$(minikube ip)/v1/feed` before you build anything on top of it. If that hangs, you must port-forward instead and point your script at the forwarded port:
> ```bash
> kubectl -n ingress-nginx port-forward svc/ingress-nginx-controller 18080:80 &
> curl -H 'Host: rpd311.local' http://localhost:18080/v1/feed
> ```
> Decide which of these two your `golden-path.sh` uses **before** Step 2, because it determines your Dev environment's base URL. Linux users can generally use `rpd311.local` directly.

### Repo secrets and config

- [ ] `SERVICE_TOKEN` — the internal `X-Service-Token` shared secret. The committed demo value is `changeme-service-token` in `k8s/base/secret-local.yaml`. You will need it in Step 4/5 (see the auth note there).
- [ ] `POSTMAN_SERVICE_ACCOUNT_KEY` exported in your shell. **Never commit it.**

---

## ✅ Step 0: Get a green baseline first

**Do not start the Postman work until the application stack is provably healthy.** Most capstone failures are broken clusters misdiagnosed as broken Postman automation, and you will burn hours on the wrong layer.

```bash
# 1. Build the three images into minikube's docker daemon
eval "$(minikube docker-env)"
for svc in reports-service triage-service status-service; do
  docker build -t "rpd311/$svc:1.0.0" "services/$svc"
done

# 2. Apply in this order — the services crash-loop without datastores
kubectl apply -f k8s/base/namespace.yaml
kubectl apply -f k8s/base/configmap-common.yaml
kubectl apply -f k8s/base/secret-local.yaml
kubectl apply -f k8s/dev/datastores.yaml        # ← easy to miss, non-optional
kubectl -n rpd311 rollout status deployment/postgres
kubectl apply -f k8s/reports-service/
kubectl apply -f k8s/triage-service/
kubectl apply -f k8s/status-service/
kubectl apply -f k8s/ingress/ingress-local.yaml

# 3. Prove the whole call graph works, end to end
kubectl -n rpd311 port-forward svc/reports-service 3001:80 &
kubectl -n rpd311 port-forward svc/triage-service  3002:80 &
kubectl -n rpd311 port-forward svc/status-service  3003:80 &
cd e2e && pip install -r requirements.txt && pytest -q
```

`pytest -q` green means submit → triage → callback → acknowledge → public status/feed/stats all work. **Only then** proceed to Step 1.

> ⚠️ **If the ingress apply is rejected**, you will see this:
> ```
> Error from server (BadRequest): error when creating "k8s/ingress/ingress-local.yaml":
> admission webhook "validate.nginx.ingress.kubernetes.io" denied the request:
> nginx.ingress.kubernetes.io/configuration-snippet annotation cannot be used.
> Snippet directives are disabled by the Ingress administrator
> ```
> Modern ingress-nginx — including the version the minikube `ingress` addon installs — refuses snippet annotations. **Fix: delete the `nginx.ingress.kubernetes.io/configuration-snippet` block from `k8s/ingress/ingress-local.yaml`** and re-apply. It is safe to remove and changes nothing you need: nginx forwards `traceparent`/`tracestate` to upstreams by default, and more importantly each service *originates* its own trace when the inbound request has none (see `deriveOutboundTraceparent` in `services/reports-service/src/middleware/tracing.js`). Your Service Graph in Step 6 does not depend on the ingress passing that header. Newer copies of this repo already have the annotation removed.
>
> While you are in that file: if `kubectl apply` warns that `kubernetes.io/ingress.class` is deprecated, replace the annotation with `ingressClassName: nginx` under `spec:`.

Note that the images use `imagePullPolicy: IfNotPresent` with local tags and there is no registry — building inside `minikube docker-env` (or `minikube image load`) is how they reach the node.

---

## 🛠️ The Headless Orchestration Loop

```
[ Local Code Edit / Branch Trigger ]
                  │
                  ▼
┌──────────────────────────────────┐
│   1. Machine Authentication      │ ──► Exchange Service Key for short-lived JWT token
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│   2. Workspace Provisioning      │ ──► Programmatically spin up Team Workspace & Environments
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│   3. Schema Ingestion & Sync     │ ──► Push all three `openapi.yaml` to the API Catalog
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│   4. Collection/Test Generation  │ ──► Turn schema into an executable contract test suite
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│   5. Multi-Stage CLI Gating      │ ──► Run Postman CLI (--report-events DEV & TEST)
└─────────────────┬────────────────┘
                  ▼
┌──────────────────────────────────┐
│   6. Production Traffic Ingestion│ ──► Deploy Workspace-Mode Insights Agent to minikube
└──────────────────────────────────┘
```

---

## 🏗️ Step-by-Step Lab Requirements

### Step 1: Headless Machine Authentication

**The Goal:** Establish a secure machine-to-machine trust framework without exposing individual user API keys.

**Task:** Provision a Postman Service Account in your Enterprise Team Dashboard and export your Service Account Key.

**Code Requirement:** Write an authentication routine inside `golden-path.sh` that reads this key from an environment variable (`POSTMAN_SERVICE_ACCOUNT_KEY`), executes a secure POST call to the Postman Service Account token exchange endpoint, and dynamically stores the short-lived JWT service token in a session variable (`POSTMAN_API_KEY`).

**Implementation notes:**
- Fail loudly and early if `POSTMAN_SERVICE_ACCOUNT_KEY` is unset. A headless script that proceeds with an empty credential produces baffling 401s three steps later.
- Never `echo` the token. If you log the exchange response for debugging, redact it.
- Record the token's actual expiry. Step 6 depends on it.

> ⚠️ **Verify as you go — Step 1:** Confirm the current token-exchange endpoint path, request shape, and response field name from Postman's live API docs, plus the **real TTL**. Everything downstream assumes this token is valid for the duration of your script run.

---

### Step 2: Programmatic Workspace & System Environment Provisioning

**The Goal:** Spin up completely isolated, reproducible sandbox environments for incoming code branches.

**Task:** Programmatically create a dedicated team workspace and attach the required infrastructure environments.

**Code Requirement:**
- Call the `POST /workspaces` endpoint using your service token to create a new workspace (e.g. `RPD-311-[BranchName]`) and capture the returned `workspaceId`.
- Execute two subsequent `POST /environments` calls to dynamically create and bind a Dev Environment and a Test Environment.

**⚠️ Get the base URL right — this is the single most common failure in this capstone.**

The OpenAPI specs put `/v1` in the `servers` block and leave paths unprefixed (`/reports`, not `/v1/reports`). So the base URL your environment supplies **must include `/v1`**:

| Environment | Correct value | Wrong (404s on every request) |
|---|---|---|
| Dev | `http://rpd311.local/v1` | ~~`http://rpd311.local`~~ |
| Dev (macOS port-forward) | `http://localhost:18080/v1` + `Host: rpd311.local` header | — |

The ingress rewrites to `/v1/$1` and the services mount their routes under `/v1`, so stripping the prefix produces 404s that look like routing bugs.

**Also required — bind the variable the generated collection actually uses.** Each spec's *first* `servers` entry is `https://api.rpd311.raccoon.gov/v1`, **a fictional domain that does not resolve.** A collection generated from the spec will default to it, and every request in Step 5 will fail on DNS. Your environments must define the base-URL variable the generated collection references (commonly `baseUrl`) and override that default.

**Your environments must also carry:**
- `serviceToken` = your `SERVICE_TOKEN` value — required by several endpoints (see Step 4).
- Any `reportId` / `assignmentId` variables your generated tests need to chain requests.

> ⚠️ **Verify as you go — Step 2:** Confirm how `POST /environments` associates an environment with a workspace in the current API (a `?workspace=` query parameter, a body field, or otherwise). Then generate one collection by hand and **inspect which variable name it uses for the host** — do not assume `baseUrl`.

---

### Step 3: Automated Spec Ingestion & Cataloging

**The Goal:** Bind the localized codebase schema directly to your new workspace as the central source of truth.

**Task:** Register the service definitions inside the Postman API Catalog.

**Code Requirement:** Fire HTTP POST requests to the Postman API definitions endpoint using your `workspaceId`, pushing the raw contents of **all three** specs:

```
services/reports-service/openapi.yaml    # public write API
services/triage-service/openapi.yaml     # internal — servers[0] is cluster-internal DNS
services/status-service/openapi.yaml     # public read API
```

All three are required. The Service Graph in Step 6 and the Shadow API trap both depend on `triage-service` being catalogued, and a single-service catalog cannot demonstrate either.

**🛑 Expect governance violations — this is intentional, do not "fix" them.**

These specs deliberately violate API governance rules. The flagged findings are a teaching artifact, and pre-fixing the specs to score clean defeats the purpose. Therefore:

- **Spec-quality and governance findings do NOT gate your pipeline.** Do not let `postman api lint` (or any governance check) fail your build. If you add one, run it in report-only mode and log the findings.
- The only failures that should halt your script are the three in the Validation Gate section below.

> ⚠️ **Verify as you go — Step 3:** Confirm whether the definitions endpoint expects the spec as a raw string, base64, or multipart, and whether a spec and its API entity are created in one call or two. Also decide whether you want **Git Sync** in your pipeline at all — as written, this step is *API-based ingestion*, not a Git-linked API. Those are different mechanisms with different setup; adding Git Sync is a separate task, not a variation of this one.

---

### Step 4: Headless Collection & Test Generation

**The Goal:** Automatically generate functional request test suites straight from the schema blueprint.

**Task:** Invoke Postman's definition-to-collection engine.

**Code Requirement:** Make a `POST` request to the `/collections` import endpoint targeting your newly ingested schema, configured to auto-generate a baseline functional test suite containing variable setups, status code validations, and contract structural assertions (`pm.response.to.have.jsonSchema`). Capture the resulting `collectionId`.

**⚠️ Auth-protected endpoints will 401 unless you handle them.** A collection generated from the full spec includes internal endpoints that legitimately reject unauthenticated calls:

| Service | Endpoints requiring `X-Service-Token` |
|---|---|
| reports-service | `PATCH /reports/{reportId}/status` |
| triage-service | **all five** (`/triage`, `/triage/batch`, `/assignments/{id}`, `/queue/{dept}`, `/queue/{dept}/assignments/{id}/acknowledge`) |
| status-service | `POST /internal/cache/invalidate` |

"All green" is impossible unless you either:
1. **Supply the header from your environment** — add `X-Service-Token: {{serviceToken}}` to those requests (preferred; it exercises the real auth path), or
2. **Scope the run** to public endpoints with a folder or `--folder` filter, and state in your submission that you did so and why.

Also note: `triage-service`'s `servers[0]` is `http://triage-service.rpd311.svc.cluster.local/v1`, which is **not reachable from your laptop**. Testing it from outside the cluster requires a port-forward. Its invisibility from the edge is the point of the Shadow API trap — do not "fix" it by adding an ingress rule.

> ⚠️ **Verify as you go — Step 4:** This is the highest-risk step in the capstone. Confirm that the import endpoint can actually be *instructed via payload* to generate assertions including `pm.response.to.have.jsonSchema` — versus generating requests only, or requiring a separate test-generation feature. **Do this by hand in the UI first.** If the API cannot generate assertions, your fallback is to script the assertions into the collection yourself via the collections API, and you should scope that in early.

---

### Step 5: Multi-Stage CLI Gating (Dev & Test Tabs)

**The Goal:** Push targeted test telemetry matrixes up to separate quality dashboards using the modern Postman CLI.

**Task:** Run two isolated validation passes against the deployment endpoints.

**Code Requirement:** Invoke the Postman CLI twice within your script:

**Dev Tab Gate** — Run the auto-generated collection against your local Dev Environment variables using the specific event routing flag:

```bash
postman collection run <collectionId> -e <devEnvId> --report-events DEV
```

**Test Tab Gate** — Run the contract verification suite against your Test Environment variables using the specific event routing flag:

```bash
postman collection run <collectionId> -e <testEnvId> --report-events TEST
```

**Implementation notes:**
- Capture and check the exit code of each run explicitly. A headless pipeline that ignores `$?` is not a quality gate.
- Ensure your port-forwards (or ingress route) are live *before* the CLI runs, and clean them up after. Background them with output redirected, or the script can hang.

> ⚠️ **Verify as you go — Step 5:** Confirm that **`--report-events` is a current Postman CLI flag** and that `DEV` / `TEST` are its accepted values — run `postman collection run --help` before building around it. Also confirm whether `-e` accepts an environment **UID** (as assumed here) or requires a local file, and confirm the actual tab names in the API Catalog UI ("Dev", "Test", "Production"). If the flag does not exist under that name, find the current mechanism for routing run results to a Catalog stage; the *concept* of two stage-scoped gates is the requirement, not this exact syntax.

---

### Step 6: Production Telemetry Ingestion (Production Tab)

**The Goal:** Surface dynamic, live infrastructure metrics and mapping without human setup.

**Task:** Deploy the Postman Insights Agent configured in Workspace Mode directly to your local minikube cluster.

**Code Requirement:**
- Your script must dynamically generate and apply a Kubernetes ConfigMap/Secret containing your Postman credential and the dynamic `workspaceId` generated in Step 2.
- Deploy the Insights Agent to minikube alongside the standard RPD 311 microservices.
- Drive live traffic against the cluster so the agent has a connected call graph to observe.

**⚠️ The agent manifest is not in this repo.** `k8s/README.md` references the Insights Agent DaemonSet and Cluster Watcher as commented-out placeholders — there is no checked-in manifest to `kubectl apply`. **Authoring it is part of your work.** Start from Postman's current Insights Agent install documentation and adapt it to the `rpd311` namespace.

**⚠️ Your Step 1 token will likely expire mid-exercise.** The service token from Step 1 is short-lived (assume minutes), but the Insights Agent is a long-running workload that must keep reporting for as long as you generate traffic. Injecting a 15-minute JWT into a DaemonSet Secret means the agent stops reporting shortly after it starts. **You must handle this**, and how you do it is a graded design decision:
- provision a durable API key for the agent specifically, and reserve the short-lived service token for the control-plane calls in Steps 2–5 (simplest, and closest to real practice), **or**
- implement a refresh loop that re-writes the Secret and restarts the agent, **or**
- document explicitly that your run window is shorter than the token TTL and demonstrate it inside that window.

State which you chose and why in your submission.

**Use the traffic generator that already exists.** Do not hand-roll a curl loop — this repo ships `e2e/generate_traffic.py`, which drives the full reports→triage→status call graph including edges into the internal `triage-service`, and deliberately sends **no** `traceparent` so the services originate one themselves. That is precisely the path the Service Graph depends on:

```bash
# Against port-forwarded services (defaults match localhost:3001/3002/3003)
python e2e/generate_traffic.py -n 50 -d 0.5

# Or point it at your ingress
REPORTS_URL=http://rpd311.local/v1 \
STATUS_URL=http://rpd311.local/v1 \
TRIAGE_URL=http://localhost:3002/v1 \
  python e2e/generate_traffic.py
```

A hand-written curl loop against the ingress cannot reach `triage-service` at all (no public route), so it will not produce the internal edge the Shadow API trap requires.

> ⚠️ **Verify as you go — Step 6:** Confirm that **"Workspace Mode"** is the current name for the agent configuration you want, and whether the agent ships as a DaemonSet, Deployment, or Helm chart today. Confirm which credential type it accepts (service token vs. long-lived API key) — this determines which mitigation above is even available to you. Finally, confirm how long telemetry takes to appear in the Catalog; do not conclude your pipeline is broken after 60 seconds.

---

## 🛑 The "Three Greens" Validation Gate (Failure Conditions)

To pass the capstone, your script must successfully defend against the following architectural failures. Each is something you should **deliberately induce and then prove your pipeline catches.**

### 1. Contract Drift Failure

Introduce genuine drift between the spec and the running service — for example, add a **required response field to `openapi.yaml` that the service does not actually return**, or a required request field the service rejects.

The Postman CLI in Step 5 must catch the drift, return a **non-zero exit code**, and your script must halt the deployment.

> Note: this is drift between the *spec and the implementation*. minikube performs no spec validation of any kind — it is not a participant in this check.

### 2. The Shadow API Trap (`triage-service`)

Because `triage-service` operates via a closed ClusterIP with **no public ingress**, edge probing cannot see it. Your automation is only complete once the in-cluster Insights Agent discovers this service from *inside* minikube and populates it in the Catalog.

Do not "solve" this by adding an ingress rule for `triage-service`. Its invisibility from the edge is the entire lesson, and `k8s/triage-service/triage-service.yaml` says so in a comment.

### 3. The Missing Dependency Edge

W3C trace propagation is what builds the visual dependency map on the Catalog Overview. Prove your pipeline depends on it by **explicitly disabling it**:

```yaml
# k8s/base/configmap-common.yaml
TRACEPARENT_PROPAGATION_ENABLED: "false"    # ← set to false; do not merely delete the key
```

> ⚠️ **This must be `"false"`, not absent.** All three services **default this flag to `true` when the variable is unset** (`services/reports-service/src/config.js:33`, `services/triage-service/src/config.py:32`, `services/status-service/src/config.go:64`). Deleting the key changes nothing — tracing stays on and the graph still builds. Set it to `"false"`, restart the pods, confirm the dependency edges disappear, then restore it.

---

## 🧹 Idempotency & Cleanup (required)

Your script runs on every branch trigger, in a shared Enterprise team. Treat that as a real constraint:

- **Make it re-runnable.** Re-running `golden-path.sh` on the same branch must not create a second `RPD-311-[BranchName]` workspace. Find-or-create, don't blindly create.
- **Ship a teardown path.** Provide `golden-path.sh --teardown` (or an equivalent) that deletes the workspace it created and removes the agent from the cluster. Leaving dozens of orphaned workspaces behind is a failing outcome, not a cosmetic one.
- **Mind API rate limits.** A tight loop of Postman API calls can hit them. Handle 429 with a backoff rather than crashing.

---

## 🏁 Submission Deliverable

Engineers must submit:

1. **`golden-path.sh`** — the single master orchestration script managing the entire pipeline without human intervention, including the teardown path.
2. **A clean terminal output log** showing a passed multi-stage Postman CLI execution, with exit codes visible.
3. **A link to your dynamically provisioned Postman Workspace** showing the RPD 311 API Catalog with all three tabs (Dev, Test, Production) illuminated green. Confirm your instructor can actually view it — check the workspace's visibility and team membership.
4. **A short `DECISIONS.md`** (half a page) covering: how you handled the agent credential lifetime (Step 6), whether you supplied service tokens or scoped the collection run (Step 4), and any place the current Postman API differed from this guide.
5. **Evidence for each of the three failure conditions** — a log or screenshot per condition showing your pipeline catching it.

### Suggested rubric

| Area | Points |
|---|---|
| Step 0 baseline reproducible from a clean clone | 5 |
| Steps 1–2: auth + workspace/environment provisioning, correct base URLs | 20 |
| Step 3: all three specs catalogued; governance findings logged, not gating | 15 |
| Step 4: collection generated with working auth handling | 15 |
| Step 5: two stage-scoped gates, exit codes enforced | 15 |
| Step 6: agent deployed, credential lifetime handled, Service Graph populated | 20 |
| Failure conditions 1–3 demonstrated | 15 |
| Idempotency + teardown | 10 |
| `DECISIONS.md` quality | 5 |
| **Total** | **120** |

---

## 📌 A note on this guide's accuracy

The RPD 311 codebase details in this document (file paths, config defaults, spec structure, port numbers, auth requirements) were verified against the repo. The **Postman API and CLI specifics were not** — endpoint shapes, flag names, and feature names change. Every `⚠️ Verify as you go` callout marks a claim you should confirm against current Postman documentation before you build on it. If you find one is wrong, note it in `DECISIONS.md`; that is a legitimate finding, not a failure.
