# CLI and app entry points

> Generated from main @ `40e81412e995a9b153a02ff39f3ae1aec187de25` on 2026-10-10. Index: [README.md](README.md).
> Operator detail: [`../APP_ASSEMBLY.md`](../APP_ASSEMBLY.md), [`../API_CLI_PARITY.md`](../API_CLI_PARITY.md).

## Entry points on main

| Entry | Defined in | What it starts |
|-------|-----------|----------------|
| `python -m skeleton` / `skeleton` | `skeleton/__main__.py:main` (`[project.scripts]` in `pyproject.toml`) | Command dispatcher below |
| `skeleton-dev` | `skeleton.developer.cli:main` | Developer CLI (same as `skeleton dev`) |
| `skeleton-bootstrap` | `skeleton.developer.bootstrap:main` | Developer bootstrap |
| `skeleton-repo-machine` | `skeleton.repo_machine.cli:main` | Repo machine tooling |
| `skeleton-train-local-model` | `skeleton.ai.runtime.inference.train:main` | Local model training |
| Engine API server | `Dockerfile` `CMD ["uvicorn", "skeleton.api.server:create_app", "--factory", "--host", "0.0.0.0", "--port", "8001"]` | FastAPI app; container health check hits `/api/v1/health/live` |
| `run_server()` | `skeleton/api/server.py` | uvicorn on `0.0.0.0:8000` (programmatic) |
| Windows launcher | `skeleton/app/windows_launcher.py`, `scripts/windows/build_installer.ps1` | `Skeleton.exe` installer |

## `python -m skeleton` commands

Dispatch in `skeleton/__main__.py:main`:

| Command | Handler | Notes |
|---------|---------|-------|
| `app ...` | `skeleton.app.cli.run_app_cli` | See next section |
| `run [vision] [--era E] [--out DIR] [--overwrite] [--json] [--blend A B --t T] [--generation G]` | `_cmd_gameforge_run` → `skeleton.context.pipeline.GameForgeRun.live().execute(..., target="godot")` | With no arguments it only boots Genesis and prints handle names. Exit 1 if `succeeded` is false |
| `forge [name]` | `skeleton.forge.universal.Forge` | Creates one blueprint |
| `test` | `_cmd_test` | `pytest skeleton/testing -ra`, unittest discovery fallback |
| `dev ...` | `skeleton.developer.cli.run_dev_cli` | `scaffold`, `wizard`, `health`, `visualize`, `extension`, `docs` |
| `eras` | `skeleton.forge.walk_cli.run_eras` | |
| `generations` | `skeleton.forge.hardware.catalog` | |
| `plan <vision>` | `skeleton.cortex.live.live_jeeves().plan_build` then `persist()` | |
| `cockpit <command>` | `skeleton.context.cockpit.Cockpit().apply` | |
| `walk [...]` | `skeleton.forge.walk_cli.run_walk` | |
| `doctor` | `skeleton.forge.walk_cli.run_doctor` | |
| `creator ...` | `skeleton.forge.creator.command_surface.creator_cli_payload` | Exit 2 on `CreatorCommandError` |
| `contracts` | `skeleton.application.parity_matrix` | |
| `capabilities [--<audit>]` | `skeleton.application.*_snapshot` | 35 mutually exclusive views: `--lifecycle` plus 34 audits (`--route-audit`, `--hmac-audit`, `--cortex-audit`, ...) |
| `invoke '<json>'` | `skeleton.application.invoke_unified` | Versioned envelope; boots Genesis for runtime commands |
| `command <name> ['<json>']` | `build_runtime_command_service(state).execute` | |
| `status` / `config` | shared commands `status` / `configuration` | |
| `help`, `-h`, `--help` | prints module docstring | |

Shared/invoke commands `run`, `tool`, `memory`, `admin`, `retrieve`, `plan`, `evidence` boot `Genesis(seed=42)` first (`_boot_runtime_if_needed`).

## `python -m skeleton app` (`skeleton/app/cli.py`)

| Subcommand | Flags on main |
|------------|---------------|
| `status` (default) | `--json`, `--live`, `--full`, `--timeout` (3.0) |
| `check` | `--json` (+ check options) |
| `plan` | `--full`, `--json` |
| `up` | `--full`, `--no-build`, `--verify-attempts` (12), `--verify-delay` (1.0), plus mode flags |
| `local-ai` | `--model`, `--prompt`, `--max-output-tokens` (8), `--json` |
| `down`, `ps` | — |
| `smoke` | `--full`, `--timeout` (3.0), `--attempts` (1), `--delay` (1.0), `--json` |
| `logs [service]` | `-f/--follow` |
| `config` | renders/validates Compose config |
| `preload`, `setup`, `install` | registered by `skeleton.app.installer.configure_setup_parsers`, run by `run_setup_command` |

`up`/`down`/`ps`/`logs` drive Docker Compose with the manifest in `skeleton/app/manifest.json`.

## CI exercise of the operator verbs

`ci.yml` job **Skeleton GameForge** runs, after its pytest set:
`python -m skeleton eras`, `python -m skeleton plan "soulslike extraction with bonfire rest"`, `python -m skeleton cockpit "BLEND ERA arcade_golden_age soulslike 0.5"`, `python -m skeleton walk --era soulslike`.
Job **Cockpit Smoke** is separate. Neither job runs `skeleton run --out` to a materialised Godot tree.
