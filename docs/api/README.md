# Skeleton engine HTTP API

> Generated from main @ `40e81412e995a9b153a02ff39f3ae1aec187de25` on 2026-10-10 by reading the routers that `skeleton/api/server.py:create_app()` mounts.
> Only mounted routes are listed. Architecture: [../architecture/api-gateway.md](../architecture/api-gateway.md).

Totals: **208** routes = 206 router routes + 2 inline (`GET /`, `GET /cortex/status`). Base URL in Compose: `http://localhost:${SKELETON_PORT:-8010}`.

## Access rules (summary)

- Every route passes the Gate stack (HeaderBound → RequestSeal → WriteAdmit → BodyBound → WORM → Auth → PolicyGate).
- Unsealed by default: `/`, `/health`, `/ready`, `/api/v1/health/live`, `/api/v1/health/ready`, and everything under `/api/v1/engine` (engine checks its own `Authorization: Bearer` service token).
- Extra unsealed prefixes only with `SKELETON_PUBLIC_DEV_SURFACES=1`: `/cortex/status`, `/cockpit`, `/docs`, `/openapi.json`, `/redoc`, `/api/v1/health`, `/api/v1/metrics`, `/api/v1/genesis`.
- `require_charter` additionally guards `POST /api/v1/swarm/submit`, `/api/v1/forge/blueprint`, `/api/v1/forge/materialise`, `/api/v1/forge/archetype`.
- Body ceiling 1 MiB by default (`SKELETON_GATE_MAX_BODY_BYTES`); 4 MiB `/api/v1/engine/executions`, 34 MiB `/api/v1/engine/media/images/variation`, 70 MiB `/api/v1/engine/media/images/edit`.
- Until startup completes, `RuntimeAdmissionMiddleware` rejects non-`/api/v1/health` traffic.

## Inline (`skeleton/api/server.py`)

| Method | Path |
|--------|------|
| GET | `/` |
| GET | `/cortex/status` |

## Core router (`skeleton/api/routes.py`, prefix `/api/v1`)

### Health, metrics, genesis

| Method | Path |
|--------|------|
| GET | `/api/v1/health` |
| GET | `/api/v1/health/live` |
| GET | `/api/v1/health/ready` |
| GET | `/api/v1/metrics` |
| GET | `/api/v1/genesis` |
| GET | `/api/v1/genesis/handles` |
| GET | `/api/v1/interface/reranker/stats` |
| GET | `/api/v1/capabilities` |

### Application audits (read-only, back the `capabilities --*-audit` CLI views)

| Method | Path |
|--------|------|
| GET | `/api/v1/application/routes/audit/{method}/{path:path}` |
| GET | `/api/v1/application/routes/audit` |
| GET | `/api/v1/application/hmac/audit/{method}/{path:path}` |
| GET | `/api/v1/application/hmac/audit` |
| GET | `/api/v1/application/cli/audit/{command_id}` |
| GET | `/api/v1/application/cli/audit` |
| GET | `/api/v1/application/templates/audit/{template_id}` |
| GET | `/api/v1/application/templates/audit` |
| GET | `/api/v1/application/sidecars/audit/{method}/{path:path}` |
| GET | `/api/v1/application/sidecars/audit` |
| GET | `/api/v1/application/domains/audit/{path:path}` |
| GET | `/api/v1/application/domains/audit` |
| GET | `/api/v1/application/cortex/audit/{method}/{path:path}` |
| GET | `/api/v1/application/cortex/audit` |
| GET | `/api/v1/application/mounted/audit/{method}/{path:path}` |
| GET | `/api/v1/application/mounted/audit` |
| GET | `/api/v1/application/main-cli/audit/{command_id}` |
| GET | `/api/v1/application/main-cli/audit` |
| GET | `/api/v1/application/app/audit/{method}/{path:path}` |
| GET | `/api/v1/application/app/audit` |
| GET | `/api/v1/application/charter/audit/{method}/{path:path}` |
| GET | `/api/v1/application/charter/audit` |
| GET | `/api/v1/application/contracts/audit/{command_id}` |
| GET | `/api/v1/application/contracts/audit` |
| GET | `/api/v1/application/hmac/live-audit/{method}/{path:path}` |
| GET | `/api/v1/application/hmac/live-audit` |
| GET | `/api/v1/application/nested/audit/{include_id:path}` |
| GET | `/api/v1/application/nested/audit` |
| GET | `/api/v1/application/env/audit/{flag_id}` |
| GET | `/api/v1/application/env/audit` |
| GET | `/api/v1/application/views/audit/{flag_id}` |
| GET | `/api/v1/application/views/audit` |
| GET | `/api/v1/application/idempotency/audit/{handler_id:path}` |
| GET | `/api/v1/application/idempotency/audit` |
| GET | `/api/v1/application/seal/audit/{method}/{path:path}` |
| GET | `/api/v1/application/seal/audit` |
| GET | `/api/v1/application/admit/audit/{method_id}` |
| GET | `/api/v1/application/admit/audit` |
| GET | `/api/v1/application/limits/audit/{flag_id}` |
| GET | `/api/v1/application/limits/audit` |
| GET | `/api/v1/application/shared/audit/{command_id}` |
| GET | `/api/v1/application/shared/audit` |
| GET | `/api/v1/application/stack/audit/{layer_id}` |
| GET | `/api/v1/application/stack/audit` |
| GET | `/api/v1/application/allow/audit/{handler_id:path}` |
| GET | `/api/v1/application/allow/audit` |
| GET | `/api/v1/application/version/audit/{source_id:path}` |
| GET | `/api/v1/application/version/audit` |
| GET | `/api/v1/application/authz/audit/{command_id}` |
| GET | `/api/v1/application/authz/audit` |
| GET | `/api/v1/application/open-dev/audit/{prefix_id:path}` |
| GET | `/api/v1/application/open-dev/audit` |
| GET | `/api/v1/application/tokens/audit/{token_id}` |
| GET | `/api/v1/application/tokens/audit` |
| GET | `/api/v1/application/mode/audit/{source_id}` |
| GET | `/api/v1/application/mode/audit` |
| GET | `/api/v1/application/codename/audit/{source_id}` |
| GET | `/api/v1/application/codename/audit` |
| GET | `/api/v1/application/cver/audit/{source_id}` |
| GET | `/api/v1/application/cver/audit` |
| GET | `/api/v1/application/ttl/audit/{source_id}` |
| GET | `/api/v1/application/ttl/audit` |
| GET | `/api/v1/application/planes/audit/{plane_id}` |
| GET | `/api/v1/application/planes/audit` |
| GET | `/api/v1/application/genesis/audit/{phase_id}` |
| GET | `/api/v1/application/genesis/audit` |
| GET | `/api/v1/application/capabilities/export-audit/{capability_id}` |
| GET | `/api/v1/application/capabilities/export-audit` |
| GET | `/api/v1/application/capabilities/lifecycle` |
| GET | `/api/v1/application/capabilities/{capability_id}` |
| GET | `/api/v1/application/capabilities` |

### Retrieval and memory

| Method | Path |
|--------|------|
| POST | `/api/v1/retrieval/query` |
| POST | `/api/v1/retrieval/ingest` |
| POST | `/api/v1/retrieval/feedback` |
| POST | `/api/v1/memory/query` |

### Jeeves

| Method | Path |
|--------|------|
| POST | `/api/v1/jeeves/session` |
| POST | `/api/v1/jeeves/interact` |
| POST | `/api/v1/jeeves/review` |
| POST | `/api/v1/jeeves/bind-era` |
| POST | `/api/v1/jeeves/advise` |
| GET | `/api/v1/jeeves/matrices/{session_id}` |

### Genesis swarm mesh, ledger, scheduler

| Method | Path |
|--------|------|
| GET | `/api/v1/swarm/stats` |
| POST | `/api/v1/swarm/agent` |
| POST | `/api/v1/swarm/route` |
| POST | `/api/v1/swarm/submit` |
| GET | `/api/v1/ledger/stats` |
| GET | `/api/v1/ledger/tail` |
| GET | `/api/v1/scheduler/stats` |

### Pipelines, forge, GameForge

| Method | Path |
|--------|------|
| POST | `/api/v1/pipeline/npc` |
| POST | `/api/v1/pipeline/game-logic` |
| POST | `/api/v1/pipeline/animation` |
| POST | `/api/v1/forge/blueprint` |
| POST | `/api/v1/forge/materialise` |
| GET | `/api/v1/forge/kinds` |
| GET | `/api/v1/forge/eras` |
| POST | `/api/v1/forge/archetype` |
| POST | `/api/v1/gameforge/run` |
| POST | `/api/v1/gameforge/intake` |

### Intelligence, resilience, context

| Method | Path |
|--------|------|
| POST | `/api/v1/intelligence/reason` |
| POST | `/api/v1/resilience/sanitise` |
| GET | `/api/v1/resilience/stats` |
| GET | `/api/v1/context/snapshot` |
| POST | `/api/v1/context/command` |

### GitHub OAuth

| Method | Path |
|--------|------|
| GET | `/api/v1/auth/github` |
| GET | `/api/v1/auth/github/start` |
| GET | `/api/v1/auth/github/callback` |

## Shared commands (`skeleton/api/command_routes.py`)

| Method | Path |
|--------|------|
| GET | `/api/v1/commands/contracts` |
| POST | `/api/v1/commands/execute/{command}` |
| POST | `/api/v1/commands/invoke` |

## Engine (`skeleton/api/engine_routes.py`)

| Method | Path |
|--------|------|
| POST | `/api/v1/engine/executions` |
| POST | `/api/v1/engine/admission/storage` |
| POST | `/api/v1/engine/governance/writes` |
| POST | `/api/v1/engine/governance/retention/plan` |
| POST | `/api/v1/engine/governance/deletions` |
| POST | `/api/v1/engine/governance/deletions/{plan_id}/execute-engine-targets` |
| POST | `/api/v1/engine/governance/deletions/acknowledgements` |
| GET | `/api/v1/engine/governance/inventory` |
| GET | `/api/v1/engine/executions/{execution_id}` |
| GET | `/api/v1/engine/executions/{execution_id}/handoff` |
| POST | `/api/v1/engine/executions/{execution_id}/cancel` |
| GET | `/api/v1/engine/executions/{execution_id}/tool-approvals/pending` |
| POST | `/api/v1/engine/executions/{execution_id}/tool-approvals` |
| POST | `/api/v1/engine/media/images/generate` |
| POST | `/api/v1/engine/media/images/variation` |
| POST | `/api/v1/engine/media/images/edit` |
| POST | `/api/v1/engine/media/speech` |
| GET | `/api/v1/engine/executions/{execution_id}/events` |

## Swarm durable task plane

Owned by `ServerState.swarm*`; see [../architecture/agents-swarm.md](../architecture/agents-swarm.md).

### `skeleton/api/swarm_routes.py`

| Method | Path |
|--------|------|
| GET | `/api/v1/swarm/status` |
| GET | `/api/v1/swarm/workers` |
| POST | `/api/v1/swarm/workers` |
| GET | `/api/v1/swarm/workers/{worker_id}` |
| POST | `/api/v1/swarm/workers/{worker_id}/heartbeat` |
| DELETE | `/api/v1/swarm/workers/{worker_id}` |
| GET | `/api/v1/swarm/tasks` |
| POST | `/api/v1/swarm/tasks` |
| GET | `/api/v1/swarm/tasks/{task_id}` |
| POST | `/api/v1/swarm/tasks/{task_id}/cancel` |
| POST | `/api/v1/swarm/tasks/{task_id}/revive` |
| POST | `/api/v1/swarm/workers/{worker_id}/lease` |
| POST | `/api/v1/swarm/workers/{worker_id}/tasks/{task_id}/renew` |
| POST | `/api/v1/swarm/workers/{worker_id}/tasks/{task_id}/success` |
| POST | `/api/v1/swarm/workers/{worker_id}/tasks/{task_id}/failure` |
| POST | `/api/v1/swarm/reap` |
| GET | `/api/v1/swarm/dead` |
| GET | `/api/v1/swarm/state` |
| POST | `/api/v1/swarm/state/restore` |
| GET | `/api/v1/swarm/events` |

### `skeleton/api/swarm_operator_routes.py`

| Method | Path |
|--------|------|
| GET | `/api/v1/swarm/operator/overview` |
| GET | `/api/v1/swarm/operator/hot-workers` |
| GET | `/api/v1/swarm/operator/autoscale` |
| GET | `/api/v1/swarm/operator/slo` |
| GET | `/api/v1/swarm/operator/tasks` |
| GET | `/api/v1/swarm/operator/snapshot/normalized` |
| GET | `/api/v1/swarm/operator/snapshot/compact` |
| POST | `/api/v1/swarm/operator/prune-terminal` |
| POST | `/api/v1/swarm/operator/gc` |
| POST | `/api/v1/swarm/operator/checkpoint` |
| POST | `/api/v1/swarm/operator/restore-latest` |
| POST | `/api/v1/swarm/operator/failover/elect` |
| GET | `/api/v1/swarm/operator/recovery` |

### `skeleton/api/swarm_policy_routes.py`

| Method | Path |
|--------|------|
| POST | `/api/v1/swarm/policy/admission-preview` |
| GET | `/api/v1/swarm/policy/tasks/{task_id}/worker-ranking` |

### `skeleton/api/swarm_lifecycle_routes.py`

| Method | Path |
|--------|------|
| GET | `/api/v1/swarm/lifecycle/pressure` |
| GET | `/api/v1/swarm/lifecycle/workers/{worker_id}/drain` |
| POST | `/api/v1/swarm/lifecycle/workers/{worker_id}/drain` |
| POST | `/api/v1/swarm/lifecycle/workers/reap-stale` |

### `skeleton/api/swarm_integrity_routes.py`

| Method | Path |
|--------|------|
| GET | `/api/v1/swarm/integrity/audit` |
| GET | `/api/v1/swarm/integrity/assert` |

### `skeleton/api/swarm_fence_routes.py`

| Method | Path |
|--------|------|
| POST | `/api/v1/swarm/fenced/workers/{worker_id}/tasks/{task_id}/success` |
| POST | `/api/v1/swarm/fenced/workers/{worker_id}/tasks/{task_id}/failure` |
| POST | `/api/v1/swarm/fenced/workers/{worker_id}/tasks/{task_id}/renew` |

### `skeleton/api/swarm_supervisor_routes.py`

| Method | Path |
|--------|------|
| GET | `/api/v1/swarm/supervisor/status` |
| POST | `/api/v1/swarm/supervisor/dispatch-preview` |
| POST | `/api/v1/swarm/supervisor/workers/{worker_id}/quarantine` |
| DELETE | `/api/v1/swarm/supervisor/workers/{worker_id}/quarantine` |
| POST | `/api/v1/swarm/supervisor/workers/{worker_id}/failure` |
| POST | `/api/v1/swarm/supervisor/workers/{worker_id}/success` |

### `skeleton/api/swarm_broker_routes.py`

| Method | Path |
|--------|------|
| GET | `/api/v1/swarm/broker/status` |
| POST | `/api/v1/swarm/broker/submit` |
| POST | `/api/v1/swarm/broker/workers/{worker_id}/tasks/{task_id}/success` |
| POST | `/api/v1/swarm/broker/workers/{worker_id}/tasks/{task_id}/failure` |

### `skeleton/api/swarm_batch_routes.py`

| Method | Path |
|--------|------|
| POST | `/api/v1/swarm/batch/submit` |

### `skeleton/api/swarm_ingress_routes.py`

| Method | Path |
|--------|------|
| GET | `/api/v1/swarm/ingress/status` |
| PUT | `/api/v1/swarm/ingress/tenants/{tenant}` |
| POST | `/api/v1/swarm/ingress/admit` |
| POST | `/api/v1/swarm/ingress/lease` |
| POST | `/api/v1/swarm/ingress/complete` |

### `skeleton/api/swarm_tenant_broker_routes.py`

| Method | Path |
|--------|------|
| GET | `/api/v1/swarm/tenant-broker/status` |
| GET | `/api/v1/swarm/tenant-broker/reconcile` |
| POST | `/api/v1/swarm/tenant-broker/reconcile/repair` |
| POST | `/api/v1/swarm/tenant-broker/submit` |
| POST | `/api/v1/swarm/tenant-broker/workers/{worker_id}/tasks/{task_id}/success` |
| POST | `/api/v1/swarm/tenant-broker/workers/{worker_id}/tasks/{task_id}/failure` |

### `skeleton/api/swarm_recovery_archive_routes.py`

| Method | Path |
|--------|------|
| GET | `/api/v1/swarm/recovery/archive` |
| POST | `/api/v1/swarm/recovery/archive` |
| GET | `/api/v1/swarm/recovery/catalog` |
| POST | `/api/v1/swarm/recovery/activate/{sequence}` |

## Cockpit (`skeleton/api/cockpit.py`, no prefix)

| Method | Path |
|--------|------|
| GET | `/cockpit` (HTML) |

## Defined but not mounted on main

These modules declare routers that `create_app()` does not include. Do not call them against a stock server.

- `skeleton/api/omnifabric_routes.py` (prefix `skeleton.kernel.omnifabric.doctrine.ROUTE_PREFIX`)
- `skeleton/api/cortex_routes.py`
- `skeleton/api/gameforge_routes.py` (`/gameforge/intake`, `/gameforge/run`; the mounted versions are in `routes.py`)

## Out of scope

`backend/server.py` (Compose service `backend`, prefix `/api`) is a separate FastAPI application and is not listed here.
