# deploy/ — infrastructure assets (canonical)

This is the single home for **deploy-time infrastructure assets**: environment templates, observability config and any future deploy manifests.

## Decision: `deploy` vs `deployment`

Main has three similarly named locations. They do different jobs:

| Path | What it is | Status |
|------|-----------|--------|
| `deploy/` (repo root) | Non-code deploy assets: env templates, Prometheus/Grafana config, manifests | **Canonical for infra assets.** `skeleton/pr_automation/automerge_policy.py` already classes `deploy/` under `RELEASE_PREFIXES`, and `skeleton/automation/idle_studio.py` protects it from autonomous edits. |
| `skeleton/deploy/` | Python package: deploy harness, blue/green, canary, environment manager, release notes (`skeleton.deploy.strategies`) | **Canonical Python namespace** (see `machine/repository_migration_plan.json`). |
| `skeleton/deployment/` | Compatibility shim that re-exports `skeleton.deploy.strategies` | Legacy. Don't add code here; `tests/test_repository_namespace_migrations.py` pins the shim. |

Rules for new work:
- Python deploy logic goes in `skeleton/deploy/` only.
- Config and manifests go in `deploy/` only. Never add a new top-level `deployment/`.
- Don't use `deploy/env/`: the root `.gitignore` ignores every `env/` directory, so env templates live in `deploy/environments/`.

## Layout

- `environments/`: `{backend,frontend}.{development,staging,production}.env.example`. Secret names appear with empty values only. They're validated by `backend/config/environment.py` and `frontend/scripts/validate-public-env.cjs`.
- `observability/`: Prometheus scrape config and alert rules, plus Grafana provisioning and dashboards (see `docker-compose.observability.yml`).
