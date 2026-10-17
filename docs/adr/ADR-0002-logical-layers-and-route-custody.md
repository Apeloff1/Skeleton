# ADR-0002: Logical layers and HTTP route custody

Status: **accepted**

Decision source: architecture milestone for maintainable subsystem boundaries.

## Context

Skeleton already enforces a numbered package ladder (`PY-L0` through `PY-L4`) for a high-risk slice. Contributors still describe the system as domain, application, infrastructure, and interface, and the import graph does not say which of those words a package belongs to.

Route ownership drifted the other way. `create_app` mounts charter-gated GameForge handlers on `skeleton.api.routes`. A second `gameforge_routes` module nested the command router, imported `skeleton.api.server` at module scope, and was mounted again by the dev harness on top of the same paths. Cortex's historical `register_routes` still contains `/api/v1/secrets` and must stay unmounted. On FastAPI 0.141 and later, included routers are wrapped and the current guard treats those entries as uninspectable. Internal Systems owns that guard fix in a standalone PR. This decision does not change `cortex_mount_guard.py`.

## Decision

Selected packages are classified in `machine/logical_layers.json`:

| Order | Layer | Paths |
|------:|-------|-------|
| 0 | domain | `skeleton/kernel`, `skeleton/contracts` |
| 1 | infrastructure | `skeleton/persistence`, `skeleton/observability`, `skeleton/config` |
| 2 | application | `skeleton/intelligence`, `skeleton/memory`, `skeleton/retrieval`, `skeleton/agents`, `skeleton/automation`, `skeleton/forge` |
| 3 | interface | `skeleton/api`, `skeleton/app` |

A classified module may import its own layer or a lower order. `scripts/check_architecture_logical_layers.py` fails the build otherwise. Edges that already point upward are listed by file and module. A new edge fails. An edge that disappears must be removed from the list.

`skeleton/application` stays unclassified. It is a compatibility facade over `skeleton.app.runtime`, not the application layer.

GameForge HTTP production stays on `skeleton.api.routes`. The seal-gated sidecar keeps its handlers for direct tests and does not include the command router. Command routes and the sidecar resolve `get_state` inside the dependency function. The dev harness mounts the main router and the command router, not the sidecar. Cortex routes stay unmounted. The included-router guard fix stays on the Internal Systems PR. OmniFabric and Pack H stay opt-in and unmounted.

## Consequences

Import-linter is not added. The repository already owns architecture fitness scripts, and a second linter would duplicate `machine/python_package_layers.json`. The logical-layer script is registered as `ARCH-LOGICAL-LAYERS`.

Three infrastructure modules still import application code and are named in the debt list: `skeleton/persistence/snapshots.py`, `skeleton/observability/cost_governor.py`, and `skeleton/observability/budget_accounting.py`. The cost-governor codec split adds `cost_governor_codec.py` to that list rather than pretending the dependency is gone.

This ADR does not collapse the byte-identical `skeleton/ai` mirror and does not rewrite the GameForge pipeline.
