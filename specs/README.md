# specs/

Convenience copies of the OpenAPI specs for each RPD 311 service.

**Source of truth:** specs live alongside each service in `services/<name>/openapi.yaml`.
These copies are kept in sync by CI (see `.github/workflows/ci.yaml`).

Postman Code Discovery (Lesson 3) scans `services/` for `openapi.yaml` files —
not this directory. Use `specs/` for quick reference only.

| File | Canonical location |
|---|---|
| `reports-service-openapi.yaml` | `services/reports-service/openapi.yaml` |
| `triage-service-openapi.yaml` | `services/triage-service/openapi.yaml` |
| `status-service-openapi.yaml` | `services/status-service/openapi.yaml` |
