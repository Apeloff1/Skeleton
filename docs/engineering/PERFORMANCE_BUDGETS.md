# Performance budgets and engineering gate policy

> Generated from main @ `40e81412e995a9b153a02ff39f3ae1aec187de25` on 2026-10-10. Owner: Technical Director.
> Architecture index: [../architecture/README.md](../architecture/README.md).

This page separates two things on purpose:

- **Enforced today** — limits that exist in code or CI on main, with the file that enforces them.
- **Adopted budgets** — numbers this page sets as the engineering standard. They are **not yet enforced** by any test or workflow; each one names the gate that must be built. Until that gate exists, the budget is a review standard, not a green check.

No number on this page was measured for this document. Where main records no measurement, the page says so.

## 1. Enforced today

### Request size and admission (`skeleton/api/`)

| Limit | Value | Enforced by | Override |
|-------|-------|-------------|----------|
| Header bytes | 32 768 | `request_bounds.py` `_DEFAULT_MAX_HEADER_BYTES` | `SKELETON_GATE_MAX_HEADER_BYTES` |
| Header count | 100 | `request_bounds.py` `_DEFAULT_MAX_HEADER_COUNT` | `SKELETON_GATE_MAX_HEADER_COUNT` |
| Request body (default) | 1 MiB | `middleware.py` `_DEFAULT_MAX_BODY` | `SKELETON_GATE_MAX_BODY_BYTES` |
| Body `/api/v1/engine/executions` | 4 MiB | `server.py` `_gate_body_limits` | — |
| Body `/api/v1/engine/media/images/variation` | 34 MiB | `server.py` `_gate_body_limits` | — |
| Body `/api/v1/engine/media/images/edit` | 70 MiB | `server.py` `_gate_body_limits` | — |
| Readiness | traffic rejected until engine recovery completes | `kernel/runtime_supervision.py` `RuntimeAdmissionMiddleware` | — |

### Operator probes

| Probe | Value | Where |
|-------|-------|-------|
| Container health check | 5 s timeout on `/api/v1/health/live` | `Dockerfile` |
| `skeleton app status --live` per-service probe | 3.0 s | `skeleton/app/cli.py` |
| `skeleton app smoke` | 3.0 s timeout, 1 attempt, 1.0 s delay | `skeleton/app/cli.py` |
| `skeleton app up` verification | 12 attempts × 1.0 s | `skeleton/app/cli.py` |

### CI wall-clock ceilings (`.github/workflows/ci.yml`, workflow "CI/CD")

| Job | `timeout-minutes` |
|-----|-------------------|
| Skeleton GameForge | 15 |
| Cockpit Smoke | 10 |
| Jeeves School Reasoning | 10 |
| Java Batch Accelerators | 10 |
| Assembly Vector Accelerators | 10 |
| Backend Lint | 10 |
| Backend Test | 20 |
| Backend Import Smoke | 20 |
| Frontend | 15 |
| Docker Build | 25 |

These are hang ceilings, not performance budgets: a job that takes 14 minutes passes.

### Measurement hooks that exist

- `APIGateway.card()` (`skeleton/api/gateway.py`) keeps `calls`, `errors`, `mean_ms` per route. It is not on the FastAPI request path.
- `kernel/slo.py` `SLO` counts misses against a cap (default 3). No route binds an SLO to a latency target on main.
- `p1-benchmark-registry.yml` and `vol029-retry-slo-admission.yml` exist as evidence workflows; neither fails CI on a latency regression of the engine API.

## 2. Adopted budgets (standard; gate to be built)

### Boot

| Budget | Target | Gate to build |
|--------|--------|---------------|
| `Genesis(seed=42).boot()` cold, CI runner | ≤ 2.0 s | timed test in the Skeleton GameForge job |
| API startup to `mark_ready` (no Mongo) | ≤ 5.0 s | `TestClient` startup timing test |

Boot is synchronous inside FastAPI's async `startup` and ticks four support engines inline (`bootstrap/genesis.py` `_phase_support`); it blocks the event loop for its full duration.

### Engine API latency (in-process, CI runner, warm, p95)

| Route class | p95 target | Notes |
|-------------|-----------|-------|
| `/api/v1/health/live`, `/health/ready` | ≤ 10 ms | no I/O |
| Read-only status/audit routes (`/api/v1/application/*`, `/swarm/*/status`) | ≤ 50 ms | |
| `POST /api/v1/retrieval/query`, `POST /api/v1/memory/query` | ≤ 150 ms at `k`/`top_k` ≤ 32 | Requires an upper bound on `k`/`top_k`; today only `minimum=1` is validated in `api/routes.py` |
| Swarm lease/complete (`/api/v1/swarm/workers/*`) | ≤ 50 ms | |
| `POST /api/v1/engine/executions` (accept) | ≤ 100 ms to 202 | execution itself is async |

### GameForge / creator loop

| Budget | Target | Gate to build |
|--------|--------|---------------|
| `skeleton eras` + `plan` + `cockpit` + `walk` (current CI verbs) | ≤ 60 s total | step timing in Skeleton GameForge job |
| `skeleton run "<vision>" --out <dir>` to a written Godot tree | ≤ 120 s, exit 0 | new CI step; **no CI step materialises a tree today** |

### Runtime frame budget (generated Godot projects)

| Budget | Target |
|--------|--------|
| Frame time, reference desktop | 16.6 ms (60 FPS) p95 |
| Frame time, low-end generation profile | 33.3 ms (30 FPS) p95 |

Main has no harness that runs a materialised Godot project headless and records frame time. Until one exists, no PR may claim frame-rate compliance.

## 3. Gate policy

1. **No green-except-GF.** "CI/CD" job *Skeleton GameForge* is a release gate, not a courtesy. A PR is not merge-ready if it is red, and "every job green except GameForge" is red. No new waivers.
2. **Spine before stamps.** Work that adds a stamp, audit view, or evidence workflow does not merge while a spine job (Skeleton GameForge, Cockpit Smoke, Backend Test, Frontend) is red on main for the same area, unless the PR fixes that job.
3. **Pre-existing red is reported, not absorbed.** A PR that does not touch a failing job's inputs must cite the main run id and failing step. It does not get merged as "unrelated" without that citation.
4. **Budgets need numbers.** A performance claim in a PR body must cite a measurement (command, runner, p50/p95). "Feels fast" is not evidence.
5. **No silent debt.** A known drift item goes in the "Known drift" list of [../architecture/README.md](../architecture/README.md) in the same PR that discovers it.

## 4. State of main at generation time

From GitHub Actions on 2026-10-10 (times Europe/Oslo):

- Last "CI/CD" push run on main (`79fe387`, run 37952060913, 2026-10-09 17:28): **failure**. Skeleton GameForge: success. Cockpit Smoke: success. **Frontend: failure** (eslint `import/namespace`: parse error in `frontend/src/product/journeyCatalog` at 102:94; `react/no-unescaped-entities`). **Backend Test: failure** (`tests/test_ai_chat_turn_route_cutover.py`, `tests/test_dragon_academy_routes.py`, `tests/test_engine_cross_service_boundary.py`, others). Docker Build: skipped.
- "CI/CD" does not run on docs-only changes (`paths: '!docs/**', '!**/*.md'`), so main tip `40e8141` (docs-only) has no CI/CD run of its own.
- Other push workflows on `40e8141` reporting failure include Merge Readiness, Repository machine index, P2 Repository Engineering Control, and several authority workflows (CS-300, ESS-1000, Learning-400, P3 extension/closure).
