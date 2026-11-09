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

`build_playable_game` (PR #4119, `skeleton/forge/game_builder.py`) is the only build entry. It is the wrapper around `Forge.materialise` and `godot_emit`. These callers are thin adapters over that function:

- CLI `skeleton game` (`python -m skeleton game`)
- `POST /api/v1/game/build`
- `POST /gameforge/run`
- Projects `POST /api/v1/projects/{project_id}/builds`, whose `game.build` worker calls `build_playable_game`

PR #4118 plugs the studio swarm in as the `planner` and `qa` hooks on `build_playable_game`. The default hooks are no-ops, so the CLI, the game build route, `/gameforge/run`, and the Projects worker stay on one executor.

`skeleton/api/gameforge_routes.py` belongs to #4119. This branch leaves that file untouched. #4119 makes the unmounted `/gameforge/run` handler delegate to `build_playable_game`.

Charter-gated GameForge HTTP on `skeleton.api.routes` stays the mounted surface inside `create_app`. Command routes resolve `get_state` inside the dependency function. The dev harness in `skeleton/deploy/harness.py` mounts `skeleton.api.routes` and `skeleton.api.command_routes`, and leaves the GameForge sidecar unmounted. Cortex routes stay unmounted. The included-router guard fix stays on the Internal Systems PR. OmniFabric and Pack H stay opt-in and unmounted.

`scripts/check_architecture_logical_layers.py` resolves relative imports that climb out of the current package (level 2 or more), treats `from skeleton import name` as `skeleton.name`, and checks string literals passed to `importlib.import_module` or `__import__`. A level-1 relative import stays in the current package. The debt list in `machine/logical_layers.json` is the upward edges already present; a new edge fails the build.

## Consequences

Import-linter is not added. The repository already owns architecture fitness scripts, and a second linter would duplicate `machine/python_package_layers.json`. The logical-layer script is registered as `ARCH-LOGICAL-LAYERS`.

Three infrastructure modules still import application code and are named in the debt list: `skeleton/persistence/snapshots.py`, `skeleton/observability/cost_governor.py`, and `skeleton/observability/budget_accounting.py`. The cost-governor codec split adds `cost_governor_codec.py` to that list rather than pretending the dependency is gone.

This ADR does not collapse the byte-identical `skeleton/ai` mirror. The GameForge pipeline stays behind `build_playable_game`.
