# Application Assembly

For a fresh clone, use the [current first-install guide](../README.md#first-install).
The recommended end-user launch is `python scripts/install_app.py --production --start`;
`/setup` reports service, AI and optional native readiness separately. Existing
model provisioning supports explicit context choices without rewriting an issued
installation. Public browser URLs follow configured published ports in both
production builds and development. Preserve private configuration and durable
volumes when updating; rebuild changed images instead of resetting state.


This repository is being consolidated into one coherent application while
preserving the internal boundaries that already carry production behavior.

The canonical application boundary is now the `skeleton.app` package plus
`skeleton/app/manifest.json`. Docker Compose remains the process supervisor;
the assembly layer gives the repository one topology, one preflight contract,
and one operator command.

## Application surfaces

| Service | Role | Public development endpoint |
| --- | --- | --- |
| `frontend` | Expo / browser interface | `http://localhost:3000` |
| `backend` | Skeleton application API | `http://localhost:8001` |
| `skeleton` | Skeleton v16 engine API | `http://localhost:8010` |
| `mongo` | durable state | local-only host binding |
| `chroma` | optional vector store | `http://localhost:8000` with `--full` |

**Chroma persistence is not ready for durable use.** The pinned Chroma 1.5.9
image loads `/config.yaml` with `persist_path: /data`. Its configuration loader
does not use the Compose `PERSIST_DIRECTORY` setting, and the existing
`chroma_data` volume is mounted at `/chroma/chroma`, not `/data`. Data written
to `/data` can therefore reside in the container's writable layer and be lost
when that container is removed. Health checks do not establish persistence.
The default profile does not start the optional Chroma service.

If Chroma has been used, preserve its existing container and the legacy
`chroma_data` volume before starting, recreating or removing services. Quiesce
clients and stop Chroma gracefully; retain a complete, consistent backup of its
`/data` directory, including SQLite journals, and a separate backup of the
legacy volume. Verify the backups and their integrity before planning migration.
Do not automatically combine or overwrite the two stores. App-owned `app down`
and the Windows launcher Stop now stop declared services without removing their
containers. App-owned Compose calls also disable automatic orphan removal even
when `COMPOSE_REMOVE_ORPHANS` is set in the environment. Direct `docker compose down`, older app versions and Compose
recreation can still remove the container and its writable-layer data. App-owned
`up --full` and `install --full --start` are blocked until a durable `/data`
layout and migration are qualified; ordinary default-profile startup is available.
Preserve both sources until their authority is resolved.

For an existing installation, a **non-destructive custody backup** command
is available after an operator quiesces all Chroma writers and stops the old
Chroma container. Keep the backup outside the repository:

```bash
docker stop tutolage-chroma
python scripts/chroma_backup.py --output "$HOME/chroma-custody-backup"
python scripts/chroma_backup.py --verify "$HOME/chroma-custody-backup"
```

This reads the stopped container's `/data` and legacy
`/chroma/chroma` mount separately, records bounded SHA-256 file manifests,
rechecks container identity and mounts, and refuses existing destinations,
links, unsafe state and unexpected mounts. It rejects restarts during copying
and uses no-replace publication so a concurrently created destination is not
overwritten. Offline `--verify` rehashes both copied stores and rejects missing,
modified, extra or linked files. A matching unsigned manifest does not prove
authenticity, SQLite consistency, source authority or safety of restoration.
Use the supported Linux or WSL filesystem path for this procedure; native
Windows ownership and ACL semantics have not been qualified. It does **not** remove the
container, change volume mounts, restore data, prove SQLite consistency or
authorize `--full` startup. Verified restore, database integrity, writer
fencing and recreation evidence remain mandatory before migration acceptance.
Keep the original container and both stores after backup success.

The backend and Skeleton API remain separate processes during consolidation.
Combining them prematurely would create route, dependency, startup, and
security regressions. They are one application at the operational boundary
and can be progressively reconciled behind that boundary.

The canonical displayed application name is **Skeleton** and the canonical
application version is **16.0.0**, matching the Python package and engine API.
Expo uses the same display name and application version. Existing mobile slug,
URL scheme, bundle identifier, Android package identifier, iOS build number,
and Android versionCode remain stable in this pass so identity convergence does
not silently break installed-client upgrade compatibility.

## Native desktop AI without Docker

The installed desktop launcher now has a **Local AI (offline)** action.
It opens a dedicated, native Tk conversation window using the existing
`NativeRuntimeLocalModel`, `LocalInferenceEngine` and content-addressed
local artifact loader. This path performs real CPU inference, not a scripted
or HTML demonstration. The model must come from a previously created native
Skeleton checkpoint: the installer does **not** include trained weights and
does not download them.

```bash
# On a machine with Python + Tk, without Docker/Mongo/hosted-provider tokens:
python -m skeleton app local-ai

# Headless model inference with a bound JSON receipt, for scripts/automation:
python -m skeleton app local-ai --model ./native-runtime.json \\
  --prompt "hello" --max-output-tokens 8 --json

# From the Windows installer (no system Python required):
Skeleton.exe --local-ai
```

Use **Load checkpoint…** to open a `write_local_model_artifact`-compatible
native transformer JSON artifact. File size, duplicate keys, SHA-based model
identity, runtime/tokenizer graph, and all checkpoint fields are validated by
the canonical artifact and native runtime owners before inference. The
window carries conversational context within the model's finite token budget,
drops only oldest *full* turns when required, offers generation cancellation,
and only commits a turn to its session history after the local inference
receipt is complete. No tools, providers or network transport are granted by
this window. The local transcript is ephemeral and discarded on close; the
canonical governed assistant/workspace remains the durable product authority.

**Scope:** this is an independently usable local desktop execution surface,
not a claim that the complete product shell, all 421 masterplan volumes, advanced
model quality, multimodal inference, autonomous learning, native weights,
security qualification or installation acceptance are finished. Docker is
still required by the existing full frontend/backend/Mongo service profile.
Windows `Skeleton.exe`/Inno Setup must still be built and smoke-tested on a
Windows runner before this mode can be described as shipped.

Targeted source validation:

```bash
python -m unittest tests.flgb.test_desktop_offline_ai -v
python -m unittest tests.flgb.test_flgb_02_native_local_provider -v
python scripts/check_ai_app_construction.py
python scripts/check_architecture_map.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
```

## Deep source preflight and credential custody

The read-only preloader now validates the three actual Docker build contexts
(engine at the root, backend at the root and frontend in its subtree). It
checks bounded Dockerfile and ignore-rule inputs, literal COPY sources,
wildcard match counts, missing build prerequisites, symlink admission, and
required exclusions for private runtime files. It separately verifies that
all backend Python/Alpine stages share one reviewed immutable image identity,
and that the Python version satisfies the pinned dependency compatibility
guard. Missing inputs and incompatible bases must fail before creating
secrets or starting Docker. These checks do not prove a completed image build,
dependency resolution, or native AI execution.

The Windows installer must package `Dockerfile.dockerignore` as well as
`backend/Dockerfile.dockerignore` and `frontend/.dockerignore`. The root
per-Dockerfile ignore is not interchangeable with the generic
`.dockerignore` policy. A missing installed policy is a first-install
failure, not permission to build with an expanded source context.

`app check --runtime`, `app doctor` and `app status` use bounded,
read-only private configuration input. A linked, non-regular, oversized,
changed or non-UTF-8 `.env` is rejected; the CLI reports a redacted
configuration failure and does not dispatch live doctor probes.
`app setup` remains the sole owner of permission repair and atomic writes.
A failed reader never resets an existing Mongo credential or deletes data.

Focused source qualification for the combined preinstall changes:

```bash
python scripts/check_app_assembly.py
python scripts/check_app_compose_parity.py
python -m pytest -q skeleton/testing/test_app_assembly.py skeleton/testing/test_app_install_source_contracts.py skeleton/testing/test_app_installer.py skeleton/testing/test_windows_installer.py
python -m compileall -q skeleton/app
```

These source checks are deliberately separate from a real fresh Windows/WSL2
Docker Compose build, HTTP E2E acceptance, verified restore and guarded local
model execution. Neither simulated tests nor source preflight certifies
installer release readiness.

## Setup and installer plane

The canonical first-run path is split into three bounded layers:

- `preload` is read-only. It validates Python, pip, Docker Compose, repository
  structure, and disk headroom before setup mutates anything.
- `setup` creates or repairs `.env` atomically. It generates local Mongo,
  JWT and backend-to-engine service secrets when required, preserves valid existing values, never prints
  secret values, and can rotate locally generated credentials explicitly.
- `install` composes the two phases, optionally installs the Python package,
  validates runtime prerequisites, and validates the rendered Compose topology.
  `--start` extends the transaction through application startup and readiness.

```bash
python3 -m venv .venv
# Linux/macOS; Windows uses .\.venv\Scripts\Activate.ps1
source .venv/bin/activate

python -m skeleton app preload
python -m skeleton app setup
python -m skeleton app install

# Bootstrap before the package has been installed into the interpreter
python scripts/install_app.py

# Existing managed Python environment
python -m skeleton app install --skip-python

# Install, build, start and verify the complete runtime
python -m skeleton app install --start
python -m skeleton app install --start --production

# Distinguish host/configuration, service health and actual AI availability:
python -m skeleton app doctor
python -m skeleton app doctor --live --json
```

On a live full installation, the installer now requires both reachable service
health endpoints and the backend's canonical critical-router inventory. The
`critical-api-routes` receipt phase fails if any designated first-party API
router failed to mount or registration cannot be observed. Inspect
`/api/health/registry` and `app doctor --live --json`: the
`critical_routes.observed` and `critical_routes.ready` fields must both be
`true`, with `critical_routes.missing` empty and `services_ready` true.
This is separate from trained-model availability, crawler admission, native
Windows binary verification, and first-install/playthrough acceptance.

The installer does not silently install Docker or elevate privileges. Missing
host dependencies fail closed with a remediation message. Setup writes only to
the ignored local `.env` file; installer receipts contain key names and phase
status, never generated secret values.

Older installations with a missing, placeholder or invalid-length
`SKL_ENGINE_SERVICE_TOKEN` are repaired by rerunning `app setup`. Runtime
preflight requires a normalized token of 32–4096 characters, matching the
engine client contract. Both services receive the same generated value from
Compose. After explicitly rotating secrets, restart backend and engine together
so their authentication values agree. Generic secret rotation preserves local
Mongo credentials, GameForge account signing and persistent seal/signing keys.
Changing database credentials requires a coordinated authenticated migration.
Keep the previous private environment backup for rollback; never attach it to
diagnostic reports. Setup alone does not install trained AI weights or prove
model readiness.

The host preloader checks that the selected Docker daemon is reachable, in
addition to finding the Compose plugin. Python dependencies come from
`pyproject.toml`; `requirements.txt` delegates to that same metadata. Host
Node 24+ and Yarn 1.22.22 are only prerequisites for a host Expo process;
Compose supplies them in its frontend image.

Setup also creates a separate persistent `GAMEFORGE_JWT_SECRET` for the existing
account/login authority. Restarting the backend therefore retains its signing
identity. No default-password administrator is created. Public registration
creates a viewer; administrative/editor work requires an explicitly granted
role. To bootstrap an operator, create a private UTF-8 password file locally
(at least 16 characters, at most 72 UTF-8 bytes), then run:

```bash
python -m skeleton app setup --admin-email operator@example.com \
  --admin-password-file /private/path/operator-password.txt
python -m skeleton app up --no-build
```

On Unix the password file must have private permissions (`chmod 600`). The
password is read from that file rather than from command arguments, and is
never printed in setup receipts. Configure both inputs together. The existing
auth bootstrap reads the explicitly configured pair on the next backend
startup; first-user registration is never silently elevated. The same pair of
options is available on `app install`.

Minimal startup defaults to `SKIP_HEAVY_SEED=true`. Auth/index bootstrap and
small agent collection initialization remain; large generated book/code
libraries, launch-prefill and automatic Android installation are skipped.
Those generated records are not learned or crawled evidence. Bulk sample
content is an explicit operator opt-in with `SKIP_HEAVY_SEED=false`.
The existing optional Curiosity research worker is disabled initially with
`CURIOSITY_IDLE_ENABLED=false`; its existing state stays under the durable
backend volume rather than the read-only application source directory.

`app doctor` is read-only. Without `--live`, capabilities are **not probed**.
With `--live`, it reads existing application health and canonical AI provider
inventory, without sending a model request, starting a crawl or loading an
emulator. Unavailable AI is separate from healthy application services.
Reports contain no provider key, Mongo URI, JWT value or rendered Compose
environment. `app config` validates with `docker compose config --quiet`.

### Configure real AI

The [first-install AI and crawler guide](ai/FIRST_INSTALL_AI_AND_CRAWLER.md)
covers the optional pinned provisioning command and authenticated crawler
workflow. Provisioning is an operator action; the browser never runs a shell.

Fresh `.env` files use `AI_PROVIDER=local` with both local model paths empty.
AI remains unavailable while Mongo, the APIs and the product shell can start.
Do not use a placeholder API key to simulate readiness.
Setup prepares the operator-owned local model directory before Compose starts,
so a later explicit provisioning command can use it. Existing assets are kept;
an inaccessible empty directory requires an ownership repair or a different
`SKELETON_LOCAL_MODEL_DIR`, rather than being overwritten.

For an existing trained native Skeleton artifact, copy it into the persistent
engine data volume, then edit the **private** `.env`:

```bash
docker compose cp ./trained-model.json skeleton:/app/data/local-model.json
```

```dotenv
AI_PROVIDER=local
AI_LOCAL_MODEL_PATH=/app/data/local-model.json
AI_LOCAL_DEPLOYMENT_PATH=
```

An arbitrary JSON file does not become trained weights; the canonical loader
must validate the artifact. Compose paths refer to files **inside** the engine
container. Host filenames are not automatically mounted.
`AI_LOCAL_DEPLOYMENT_PATH` accepts a pinned GGUF deployment when an
operator-provisioned compatible llama.cpp executable, shared libraries and exact
model files exist at the manifest's container paths. The base image does not
include llama.cpp or model weights. For the existing host GGUF chat/workspace
path, use the standalone commands in the README.

For hosted OpenAI execution, set `AI_PROVIDER=openai`, configure a genuine
`OPENAI_API_KEY` and the intended `AI_MODEL` in private `.env`, and leave local
model paths empty. The engine image includes the `hosted-inference` extra;
credentials and provider calls remain engine-owned. The backend and frontend
receive no model-provider key. Existing architecture, governance and provider
availability checks still apply.

After changing model configuration:

```bash
python -m skeleton app up --no-build
python -m skeleton app doctor --live
```

Readiness establishes runtime admission, not useful response quality. The
doctor performs no inference. Operator-approved emulator cores, firmware,
toolchains and crawler source/egress permissions are separate optional
capabilities; setup does not bundle or approve them.

### Startup failures and retained state

Package installation and Compose builds have finite installer budgets.
Failures return phase receipts and remediation commands without
credential-bearing subprocess output. Inspect `app doctor`, `app ps` and
`app logs <service>` locally. Treat logs as private operational data.

`FRONTEND_PORT`, `BACKEND_PORT`, `SKELETON_PORT` and `MONGO_PORT` must be valid,
distinct host ports. Startup health probes honor them. Browser
`EXPO_PUBLIC_*` endpoint overrides must also match your deployment; Docker
service names do not resolve in the browser. Production exports embed these
public endpoints at build time, so rebuild the frontend after changing them;
restarting an existing static image cannot change its bundle. Set
`CORS_ORIGINS` to the explicit browser origin(s), including custom ports.
A normal `app down` stops all declared profiles and retains their containers,
writable layers and database volumes. It does not remove orphans. Direct Compose
teardown is not protected by this app-owned behavior. Ordinary startup failures do not require
deleting volumes or rotating secrets.

### Pre-compilation readiness

Before creating any installer or claiming the assembled app can ship, run the
read-only contract pass from a configured development environment:

```bash
make precompile
```

This sequences the architecture map, AI construction and capability interfaces,
provider bootstrap, app assembly, toolchain contract, and structural application
checks. It does **not** install dependencies, mutate `.env`, launch Docker,
compile release binaries, train the model, or qualify an enterprise release.
A passing pre-compilation contract pass is necessary but not sufficient for
a completed app; it must be followed by exact-head build, runtime journey,
security, Windows installation, and independent release evidence.

The Windows build compiles both frozen executables and the Inno Setup recipe
from the same `git archive` source revision as the installed payload. The
payload is expanded with **all** `required_paths` declared by the archived
`skeleton/app/manifest.json`, and it fails before compilation if any file is
missing, a path exceeds the Windows portability budget, or its project version
differs from the requested installer version. The Windows CI interpreter is
aligned to the Python 3.11.16 toolchain baseline and the application package's
Pydantic minimum. Build failures release the temporary drive so repair attempts
are not blocked by stale mappings.

### Windows Setup.exe

The Windows distribution wraps the same setup/runtime plane in two executable
layers:

1. `Skeleton-Setup-<version>-windows-x64.exe` is the normal Windows installer
   wizard produced by Inno Setup. It installs per-user under
   `%LOCALAPPDATA%\\Programs\\Skeleton`, registers uninstall metadata, creates
   Start Menu shortcuts, and can add an optional desktop shortcut.
2. `Skeleton.exe` is the installed setup/runtime control surface. It is frozen
   with PyInstaller and carries its own Python runtime, so the user does not
   need a system Python or pip installation.

The launcher provides system check, install/repair, start, open-app, and stop
controls. Runtime setup remains fail-closed and reuses the canonical
`skeleton.app` preloader and installer implementation.

Docker Desktop with the Docker Compose plugin remains an explicit prerequisite
for running the assembled services. The installer does not silently elevate or
install Docker on the user's behalf.

Build the Windows installer on Windows with:

```powershell
pwsh ./scripts/windows/build_installer.ps1
```

The output directory contains the Setup executable plus a SHA-256 sidecar:

```text
dist/windows/Skeleton-Setup-16.0.0-windows-x64.exe
dist/windows/Skeleton-Setup-16.0.0-windows-x64.exe.sha256
```

The `Windows Installer` GitHub Actions workflow performs the same build on a
Windows runner and publishes those files as a workflow artifact. Uninstall
stops the Compose services first and removes the generated local `.env`
secret file.


## Canonical commands

```bash
# Inspect topology and dependency-aware startup order
python -m skeleton app status
python -m skeleton app status --live
python -m skeleton app plan
python -m skeleton app plan --full

# Structural repository validation
python -m skeleton app check

# Validate Docker plus required runtime environment
python -m skeleton app check --runtime

# Build and start the core application
python -m skeleton app up
# app up waits for frontend + backend + engine readiness before success

# Full-profile startup is blocked until the persistence warning is resolved
python -m skeleton app up --full

# Inspect / operate
python -m skeleton app ps
python -m skeleton app smoke
python -m skeleton app logs backend
python -m skeleton app logs -f
python -m skeleton app config
# Stops declared services while preserving containers and their writable layers
python -m skeleton app down
```

After startup, `python -m skeleton app smoke` probes the frontend, backend health endpoint, and Skeleton liveness endpoint as one application verdict. `app up` performs the same bounded readiness verification by default; `--no-verify` is reserved for diagnostics where Compose launch success is intentionally inspected separately.

The launcher now derives startup order from manifest dependencies. `app plan` exposes the dependency layers, automatically closes over transitive dependencies, and rejects cycles. `app up` consumes the same plan, so the inspected topology and the executed topology cannot silently diverge.

The CLI never uses a shell to construct Docker commands. Service names are
validated against the manifest before they are passed to Compose.

## Runtime modes

The canonical Compose file runs application code from built images. Source
bind-mounts are isolated in `docker-compose.hot.yml`. Metro/Expo development
ports are isolated there as well, so the production topology exposes only the
browser-facing frontend port. The frontend starts only after both backend and
Skeleton engine health checks pass; Mongo remains a health-gated dependency of
the API services.

```bash
# Built development images, verified after startup
python -m skeleton app up

# Development images plus source bind mounts for hot reload
python -m skeleton app up --hot

# Production backend stage + production Nginx frontend stage
python -m skeleton app up --production
```

`--production` and `--hot` are intentionally mutually exclusive. Production
keeps the public frontend URL at `http://localhost:3000` while mapping that
host port to Nginx's container port 8080, so the same readiness manifest works
in both modes.

## Runtime configuration

Copy `.env.example` to `.env` and set at least:

- `MONGO_URL`
- `SKL_MONGO_URI`
- `MONGO_INITDB_ROOT_PASSWORD`
- `JWT_SECRET`

Optional provider/payment/seal values remain optional until the corresponding
feature is used. `app up` fails closed when required runtime values are empty
or obvious placeholders.

## Public application bootstrap

The backend exposes `GET /api/app/bootstrap` as the sanitized runtime contract
for browser and native clients. Its payload is built directly from
`skeleton/app/manifest.json` and includes the canonical application identity,
service roles, dependency layers, profile membership, and declared health
paths. It intentionally excludes runtime environment names/values, container
ports, internal URLs, and process entrypoints.

The product shell fetches this contract before probing runtime health. If the
backend itself is unreachable, it falls back to the last static health-path
contract so the engine can still be diagnosed independently. The UI surfaces
whether health came from `bootstrap` or `fallback` metadata.

Legacy `/api/health` fields remain compatibility-stable; canonical Skeleton
identity is attached there as `canonical_application` while new clients use
`/api/app/bootstrap` as the source of truth.

The backend process liveness probe is `/api/health/live`. The declared backend
readiness probe is `/api/health/ready`: it returns 503 while Mongo, required
routes, or either build-vault check are unavailable. A temporary build-vault
fallback does not count as durable storage. AI provider availability is
reported separately. If readiness fails for the vault, restore the configured
`GALAXY_BUILDS_VAULT_DIR` and its write permissions before using build features;
do not treat process liveness or the temporary fallback as proof that builds
will persist. The legacy `/api/health` endpoint does not check Mongo.

Vault selection happens when the backend starts. If it selected the temporary
fallback, first stop new builds and preserve any files in the running backend's
`/tmp/galaxy_builds_vault` outside the container without overwriting existing
artifacts. Restore the configured persistent volume and permissions, then
restart the backend and confirm `/api/health/ready` succeeds before resuming.
Review and reconcile preserved fallback files separately; do not silently merge
or delete them. Restarting or recreating a container can discard its `/tmp`
contents. Vault health checks use bounded shared workers; if a filesystem call
stalls, readiness fails while its worker remains occupied until the operating
system returns the call.

## Frontend endpoint boundary

`frontend/src/utils/apiBase.ts` is the single endpoint resolver for browser and
native clients. Backend clients consume `API_BASE`; Skeleton-engine clients
consume `SKELETON_API_BASE`.

Resolution is explicit override first, then browser same-origin for
reverse-proxied deployments, then the local assembled ports
(`:8001` backend, `:8010` Skeleton). Do not read `EXPO_PUBLIC_*_URL`
directly from feature clients.

The engine liveness contract is `GET /api/v1/health/live`; frontend health
checks must not invent a shorter `/health` path on the Skeleton service.

## Production web ingress

Ingress ownership is declared in the application manifest: the frontend owns
`/`, the application backend owns `/api`, and the Skeleton engine owns
`/api/v1`. Health paths must remain inside their owning prefix. The assembly
audit derives Nginx location/upstream expectations from this metadata and also
requires more-specific prefixes to appear before broader prefixes.

The production Nginx image is the browser-facing ingress for the assembled app.
When no explicit public endpoint override is baked into the Expo export,
`apiBase.ts` uses the browser origin. Nginx then routes:

- `/api/v1/*` to the Skeleton engine service.
- all other `/api/*` traffic to the application backend.

Development remains explicit-port based (`:8001` backend and `:8010` engine)
because the Expo development server is not the production reverse proxy.

## Assembly rules

1. New user-facing capabilities should attach to one of the declared service
   boundaries, not create another top-level application.
2. New long-running services must be added to both Docker Compose and the
   application manifest in the same change.
3. Browser-facing environment variables must use host-resolvable URLs. Docker
   service DNS names are internal implementation details and must not be
   embedded into the exported frontend bundle.
4. `python -m skeleton app check` is the minimum structural regression gate
   for assembly work; it includes the manifest dependency-graph verdict.
5. The manifest and Docker Compose must declare the same service set, and the
   Expo display name must match the manifest application name.
6. Existing subsystem work should reconcile through bounded integration
   branches based on the latest assembled `main`; do not revive the superseded
   mega-diff consolidation trunk or create a competing application root.

### Jeeves multidisciplinary specialization and mirrors

The app ships with **384 executable curriculum specialization contracts**
(16 specialties by 8 review lenses in each of gaming, AI and coding). These are
training/evaluation routes, **not** 384 separately trained neural models.
Inspect the registry without running a model:

```bash
python -m skeleton app training-modules
```

For four parallel, independent data-analysis angles, supply a rights-reviewed
multidomain manifest pointing to content-addressed train and heldout JSONL:

```bash
python -m skeleton app training-modules --dataset-manifest PATH_TO_APPROVED_MANIFEST
```

To launch **two actual CPU-process optimizers concurrently**, the operator must
supply a running-app Jeeves attestation, configured persisted SKELETON_OWN
checkpoint, explicit rights review, existing output directory, and new receipt:

```bash
python -m skeleton app training-modules --train-mirrors \
  --dataset-manifest PATH_TO_APPROVED_MANIFEST \
  --attestation PATH_TO_IN_PROCESS_ATTESTATION \
  --output-directory PATH_TO_PRIVATE_CANDIDATES \
  --receipt PATH_TO_PRIVATE_CANDIDATES/mirror-receipt.json
```

The implementation fails closed on unsupported checkpoints, missing attestation,
dataset contamination, insufficient RAM/disk, or heldout regression. It never
writes to serving weights and never auto-promotes a candidate. The mirrors
perform distinct optimizer schedules; separate blinded human/independent model
review is still required to establish improvement beyond language loss.

The installed Windows launcher also provides a **Jeeves Training Modules**
read-only catalogue panel. It validates the same manifest checksum and
specialization schema without initializing the model or changing any weights.
Windows installer CI now runs the specialist data-partition tests and executes
the installed catalogue check before native inference smoke tests.

The two real optimizer arms now select **disjoint rights-reviewed teaching
lenses**: constructive work (construct, repair, resource, portability) and
adversarial work (counterexample, edge cases, security, verification).
Both are scored against the same untouched held-out examples. If either view
lacks sufficient reviewed material in gaming, AI and coding, training aborts
before spawning optimizers; synthetic placeholder data is not substituted.

### Cinematic angle, cutscene, item and apparel simulation

The authored scene validator supports original `pan_to`, `tilt`, `dolly`,
`crane`, `orbit`, `rack_focus`, `handheld`, tracking and cut types.
Jeeves can simulate timed camera positions, look targets, yaw/pitch, focal
range, spoken-line chronology, costume mobility, and item carrying constraints
without rendering images or pretending a fitted clothing-physics model exists.

Use the installed Windows **Cutscene Multi-Sim** control with a
rights-reviewed original scene JSON, or the operator CLI:

```bash
python -m skeleton app cinematic-sim --scene my-cutscene.json \
  --output cinematic-evidence.json --candidate-output cutscene-review.jsonl \
  --workers 4 --limit 128 --frame-ms 100 \
  --yaw-offsets -30 -15 0 15 30 --pan-rates 70 100 130 \
  --fov-offsets -10 0 10 --item-mass-deltas 0 250 \
  --apparel-drag-deltas 0 15 \
  --item-variants lantern shield --apparel-variants cloak armor
```

A simulation is one continuous frame evolution; the engine audits its
collected digest chain **backwards per run without restarting the sim**.
This supplies two complementary audit/readout directions, *not* twice the
independent model training. Each distinct trace can yield two quarantined,
linked review exercises. Duplicate traces are not counted as novel evidence.
Only an independently reviewed and rights-cleared corpus may later enter
the attested candidate optimizer; no serving weights are changed here.

Use `--audit-report cinematic-evidence.json` to inspect an existing
receipt without starting a new simulation; optionally combine that with
`--candidate-output` to export review-only pairs from the existing trace
summary. Every simulation run is bounded by per-run and global frame,
memory, worker and variation budgets. Item/apparel variants may only refer
to approved source identities; voice, scene chronology and screen direction
are kept invariant. Data includes shot-level camera range, occlusion, carry
capacity, outfit mobility and reverse integrity statistics. This is a
pre-render structural simulator, **not** a playable video-rendering engine.

### Pause and resume an individual cinematic simulation

The frame control plane supports in-process `pause`, `step`, `seek`,
`resume`, `checkpoint` and hash-checked `from_checkpoint`. A paused
run can also be saved and resumed from the app CLI:

```bash
python -m skeleton app cinematic-sim --scene original-scene.json \
  --pause-after 32 --checkpoint-out paused-cinema.json

python -m skeleton app cinematic-sim --scene original-scene.json \
  --resume-checkpoint paused-cinema.json --output resumed-cinema-report.json

python -m skeleton app cinematic-sim --audit-report resumed-cinema-report.json
```

The cursor stores already observed frames with a chained checksum. Restoration
rejects tampered observations and changed source identities, then computes only
remaining frames. It does not repeat earlier simulation steps or alter any
model weights. Paused artifacts are private and require an unused output path.

### Adaptive scenario, environment and adversarial simulator

Jeeves also includes a coverage-guided stress-rehearsal controller:
```bash
python -m skeleton app adaptive-sim --scene approved-original-scene.json \
  --output adaptive-campaign.json --draft-output review-drafts.jsonl \
  --budget 48 --workers 4 --seed 7 --frame-ms 100
```

The scheduler maximizes coverage across pursuit, rescue, combat, stealth,
dialogue and exploration; clear/fog/rain/snow/storm conditions, light, crowd,
noise, friction and approved camera/item/apparel stresses. It runs a *real*
deterministic camera/prop simulator per scenario and applies documented,
bounded **proxy** risk formulas to each observed frame. It does not render
rain, NPC crowds, acoustics or fluid physics. It compares each scenario to a
shared immutable baseline, prioritizes measured failures in a feedback stage,
and performs source-derived reverse audits without restarting a scene.

The `--draft-output` pairs situational diagnosis, one-factor repair requests
and adversarial edge-case review prompts. Every generated draft is **quarantined,
unlabelled and ineligible for optimizer updates** until independent rights,
quality, project-split and leakage review. This adds controlled evidence,
not fictitious model learning. The installed Windows launcher exposes an
opt-in **Adaptive Simulation** control.

Adaptive campaigns also materialize a **paired counterfactual ledger**:
each second-stage attack or repair records the parent scenario, changed
dimensions, exact targeted failure family, measured before/after counts and
observed reduction or regression. These are *executed* comparisons against
the original authored source, not merely plausible improvement prose.
The reverse audit and immutable campaign hash detect forged measurements.
The output stays quarantined until independent evaluator/rights approval.

### Real candidate parameter growth (no implied trained improvement)

Jeeves' persisted **Torch-stack** speaking model can now acquire *actual
trainable neurons* in every feed-forward layer by a private, candidate-only
operation. The operator selects `micro` (+12.5%), `balanced` (+25%),
`large` (+50%) or `xlarge` (+100%) of FFN width. Existing tensor rows,
token identities and optimizer counters remain pinned to the live parent,
while the new incoming FFN rows get deterministic nonzero weights and the
new outgoing columns start at zero. The widened candidate must reproduce
parent logits within a strict tolerance *before* training new weights.

This makes genuinely new optimizer-addressable parameters, without
pretending that larger weights immediately improve game production.
Growth is limited to 2,000,000 added parameters in a candidate, 16,000,000
total trainable parameters, independent operator caps, and host memory
admission. Native non-Torch checkpoints fail closed rather than silently
switching model architectures. An attested production Torch checkpoint and
approved training corpus are still required.

```bash
skeleton-jeeves-production-train --checkpoint LIVE_OWN.json \
  --expected-sha256 VERIFIED_64_HEX \
  --dataset-manifest APPROVED_DATASET.json \
  --capacity-growth balanced --max-added-parameters 500000 \
  --max-optimizer-steps 10000 --candidate candidate.json --report report.json
```

To grow the two process-isolated candidate arms differently:

```bash
python -m skeleton app training-modules --train-mirrors \
  --dataset-manifest APPROVED_DATASET.json \
  --attestation LIVE_ATTESTATION.json \
  --output-directory PRIVATE_OUTPUT_DIR --receipt PRIVATE_OUTPUT_DIR/receipt.json \
  --constructive-capacity balanced --adversarial-capacity micro \
  --max-added-parameters 500000
```

The result records original and grown parameter counts, exact new tensor
count, parent/candidate checksums, equivalence maximum error, measured
SGD updates, holdout loss/regression and withheld production promotion.
These are *capacity and candidate optimization results*, not independent
proof of improved game-design capabilities.

### Measured capability rehearsal (real training data, not test-set leakage)

The attested candidate trainer also offers opt-in **training-only hard-example
selection**. This uses the current model's actual average token log-probability
to score *approved training texts only*. It reserves both weak and easier
retention examples in gaming, AI and coding; then favors distinct specialties
and higher-loss cases. No held-out example enters this scheduler, selected
texts are content-hashed, and selection is checkpoint/resume-bound.

```bash
skeleton-jeeves-production-train --checkpoint LIVE_OWN.json \
  --expected-sha256 VERIFIED_64_HEX \
  --dataset-manifest APPROVED_DATASET.json \
  --capacity-growth balanced --max-added-parameters 500000 \
  --adaptive-replay --replay-examples 64 --max-scored-examples 128 \
  --candidate candidate.json --report report.json
```

The same switches work on `python -m skeleton app training-modules --train-mirrors`
for separate constructive and adversarial optimizer processes. The scorer
refuses unreviewed/synthetic inputs, duplicate training texts, absent domains,
nonfinite losses and source datasets above the explicit inference budget.
Validation and production promotion remain independent requirements. Increases
in trainable parameter count or training loss exposure **do not establish**
a capability uplift without blind external evaluation.

### Boomerang re-analysis queue (second and third pass without replay inflation)

The Jeeves Boomerang queue accepts **completed, rights-reviewed adaptive
simulation evidence** rather than restarting the original scene. Each
source-pinned immutable queue entry can be analyzed on return twice, using
new control settings selected from its archived camera, environment, item,
apparel and gameplay-risk observations. Old simulation frames are *never*
executed again merely to advance the queue; only newly selected
counterfactual scenarios are simulated.

```bash
python -m skeleton app boomerang-queue --create \
  --scene original-scene.json --archive adaptive-campaign.json \
  --output boomerang-0.json

python -m skeleton app boomerang-queue --advance \
  --queue boomerang-0.json --output boomerang-1.json \
  --probes 8 --workers 2 --draft-output boomerang-review.jsonl

python -m skeleton app boomerang-queue --advance \
  --queue boomerang-1.json --output boomerang-2.json --probes 8

python -m skeleton app boomerang-queue --inspect --queue boomerang-2.json
```

A persisted queue can hold 32 independent archived sources; `--enqueue`
adds a fresh original report to a **new** queue snapshot. FIFO advancement
with `--max-entries` caps work per command. The source and report files are
bound by exact byte SHA256 and original provenance; changed inputs abort
rather than silently replay incompatible evidence.

**Second pass** explores missed control combinations and previous failure
signals. **Third pass** prioritizes actual second-pass findings. Each
pass records novelty compared against *all earlier passes*: new failure
families, distinct controlled risk signatures, original/novel camera traces,
per-run forward/reverse checks and before/after targeted risk counts.
Budgeted fallback exploration is labeled as exploration, not a causal repair.
Completed entries refuse a fourth boomerang pass.

Optional `--draft-output` emits evidence-grouped, quarantined forward
diagnosis, reverse-forensic and minimize/retest proposals. Duplicate scene
sources or already-run scenario IDs are rejected. **These are not fresh
independent training examples, SGD updates or proven new model capabilities.**
The Windows GUI has a **Boomerang Sim Queue** control for explicit creation
and one-pass advancement. Neither the GUI nor CLI automatically modifies
Jeeves's serving weights.

### Randomized boomerang reshuffle after pass three

Previously completed three-pass boomerang queues can now be migrated into a
**versioned, audit-preserving randomized-return queue**, without losing a
single earlier observation or rerunning an original simulation:

```bash
python -m skeleton app boomerang-queue --reshuffle \
  --queue boomerang-2.json --output boomerang-scheduled.json \
  --shuffle-seed 1234 --min-return-seconds 3600 \
  --max-return-seconds 86400 --max-return-visits 16 --plateau-limit 10

python -m skeleton app boomerang-queue --inspect \
  --queue boomerang-scheduled.json

# One manual scheduler tick; only work due at the current UTC time runs.
python -m skeleton app boomerang-queue --advance \
  --queue boomerang-scheduled.json --output boomerang-next.json \
  --max-entries 2 --probes 8 --workers 2

# Optional continuously running local foreground scheduler.
python -m skeleton app boomerang-queue --watch \
  --queue boomerang-scheduled.json --output-directory ./boomerang-archive \
  --max-watch-runs 16 --poll-seconds 60 --probes 8 --workers 2
```

The scheduler uses a deterministic SHA-256-seeded pseudorandom draw within
the operator's actual wall-clock min/max interval. That makes the interval
randomized yet independently recomputable from pinned evidence, seed, pass
digest, return index and schedule time. Due historical simulations are
reshuffled alongside fresh second-/third-pass work, with aging so due older
work is not starved. Both the source and original full campaign remain pinned.

Every after-third-pass revisit executes **new effective controls** only,
preserves the old pass history and records independently audited forward and
reverse observations. It measures new **failure contexts** across situation,
weather, lighting and attack, deliberately *not* counting seed-only or
micro-camera adjustments as new discoveries. A consecutive no-new-context
plateau retires the source (default 10 returns), as does the hard 16-return
cap. Both limits and the interval range are operator-configurable.

The optional `--watch` executor runs only as an explicit, live local
process. It waits for actual UTC due times, writes every queue generation to
a new immutable filename, and stops on retirement or the configured cycle
cap. It is not an always-on service unless the operator runs it as one.
No autonomous checkpoint training or live-model promotion is performed.


## Strict installed-runtime observation

After a reviewed source checkout has started the services, run:

    python -m skeleton app qualify-install --source-head REVIEWED_SHA --json

For a checkout-based installation, add
--qualification-source-head REVIEWED_SHA to the existing install --start
command to require the same observation before its successful exit. Optional
--require-protected and --require-ai on qualify-install (or their
--qualification-require-* installer equivalents) require observed protected
writer custody and selected-provider availability respectively. They do not
enable either service.

The strict path checks setup/product HTML, exact public bootstrap contract,
direct backend and engine identity, both aggregate routes, route inventory and
selected-provider availability in at least two independent rounds. It binds
the host source SHA and private configuration identity before and after each
round, denies contradictory status bodies, requires consistent product
attestation and rejects redirects, proxies and oversized/nonfinite JSON.
A subprocess imposes a hard deadline even on slow-drip HTTP responses.
The output has fixed finding codes and redacted bounded facts, never raw
response bodies or private configuration digests.

This is stronger than a socket health check but not signed image provenance,
browser JavaScript execution, actual inference, storage restoration, Windows
device acceptance or release qualification. The default setup UI recovery
remains available and protected startup is not enabled by this command.

### Isolated corrected Chroma persistence qualification

The corrected physical layout is independently tested by
scripts/qualify_chroma_persistence.py --source-head REVIEWED_SHA
--isolated-ci-fixture. It uses the exact pinned image ID, a uniquely
generated local named volume mounted at /data, loopback-only ports and
synthetic vector records. It checks collection identity, full vector/document/
metadata equality, nearest-neighbor results, same-container restart,
durable update/delete, and a genuinely new container with the same volume.
Resource deletion is restricted to separately verified fixture ownership.
The legacy full profile remains blocked until independently reviewed
backup selection, restoration, real application integration and device
qualification succeed. This fixture never starts or modifies legacy Chroma.

### Recovery staging for the two historical Chroma stores

After the complete legacy backup has been reviewed, observe both candidate
inventories without selecting authority:

    python scripts/stage_chroma_recovery.py --backup /private/backup --inspect-candidates

An independent reviewer chooses exactly one store and signs StageApproval
from the script, binding the full original manifest hash, selected inventory
hash, exact reviewed source SHA, deployment, authority, selection and
quiescence evidence hashes, and a validity window no longer than 30 minutes.
Do not infer the authoritative store from file count, timestamps or size.
The signer retains the private key outside the application.

    python scripts/stage_chroma_recovery.py --backup /private/backup \
      --output /private/staging/new-stage --plan /private/stage-plan.json \
      --signature /private/stage-plan.sig --authority AUTHORITY --deployment DEPLOYMENT \
      --source-head REVIEWED_SHA --operator-public-key-hex PUBLIC_KEY

The stage parent must already be a private mode-0700 POSIX directory. The
new stage holds only the selected store in data/ and a redacted receipt.
Both original store copies are verified before and after the stage; every
copied descriptor is checked against exact size and content pins. The
staged SQLite is checked read-only for integrity, foreign keys and expected
schema without repairing the original. An unresolved SQLite WAL/SHM/journal
requires separate recovery; the tool intentionally refuses to ignore it.
No replace, merge, live restore, graph integrity or full-profile acceptance
is claimed. Use the isolated physical fixture for new-volume evidence and
independently qualify a staged restore on the exact pinned Chroma image.


### Persistent checkout installer recovery (POSIX)

To retain each mutating phase across process interruption, create a private
mode-0700 state directory outside the checkout and invoke the existing
installer with --session-dir, --session-id and --session-source-head:

    python scripts/install_app.py --production --start \
      --session-dir /private/install-state --session-id first-install \
      --session-source-head REVIEWED_SHA

The same state directory excludes other cooperating installers of that
checkout. Each setup, package, Compose and startup intent is fsynced before
execution. Each outcome is appended with strict identity, sequence and
hash-chain custody. Neither environment values, private fingerprints nor
raw child errors are printed by the session observation.

    python -m skeleton app inspect-install-session --session-dir /private/install-state \
      --session-id first-install

Resume an interrupted/blocked session only with the identical source SHA,
options, state directory and ID plus --resume-session. The current private
configuration must match the last recorded observation. Resume re-runs the
normal idempotent installer, including validation, rather than trusting old
passes or skipping uncertain stages. It never deletes images or volumes,
reverts migrations or rotates secrets. If setup was interrupted after an
unobserved .env change, preserve that file and independently reconcile before
opening a new session. Explicit admin credentials and secret rotation are
excluded from this recovery mode. Windows launcher behavior remains
unchanged; this POSIX implementation is not a Windows ACL qualification.


### New-install durable Chroma provisioning (operator-gated)

After the exact-source disposable Chroma persistence job succeeds on the
same image ID, independently review and pin its JSON receipt. The default
stack must already have its canonical engine and local Compose network running.
For genuinely new storage only, the separate provisioner creates the new
named volume at /data and starts only its verified owned container:

    python scripts/provision_fresh_chroma.py --source-head REVIEWED_SHA fresh \
      --fixture /private/fixture.json --fixture-sha256 REVIEWED_FILE_SHA256 \
      --port 8000 --journal /private/chroma/new-attempt.json

The private journal is fsynced before creation. A distinct created receipt
is committed before the first start. Existing legacy containers or volumes
block the fresh path. Existing corrected deployments can be observed or
started by exact created-receipt pin:

    python scripts/provision_fresh_chroma.py --source-head REVIEWED_SHA inspect-existing \
      --receipt /private/chroma/new-attempt.created.json --receipt-sha256 REVIEWED_FILE_SHA256
    python scripts/provision_fresh_chroma.py --source-head REVIEWED_SHA start-existing \
      --receipt /private/chroma/new-attempt.created.json --receipt-sha256 REVIEWED_FILE_SHA256

The operator is responsible for independently authenticating the fixture
and created receipts and selecting the appropriate local port. An uncertain
attempt is never recreated automatically. Preserve all resources for review.
The exact image, volume and container identities, bridge membership, loopback
port and service alias are checked, but production application vector
integration, legacy migration and release remain held. The old full-profile
Compose definition remains unchanged and must not be used to recreate the
corrected service. No production resources are touched by source qualification.


### Exact image construction and independently approved runtime identity

For a clean reviewed checkout, use a pre-existing private work parent outside
the repository. This explicit operator build extracts only an exact Git
archive, verifies source file identities before and after each image build,
and builds isolated production candidate tags for the engine, backend and
frontend. No existing service container, original installation image tag,
or production volume is started or replaced.

    python scripts/qualify_first_install_images.py --source-head REVIEWED_SHA build \
      --work-parent /private/builds --receipt /private/builds/review.json \
      --backend-origin http://127.0.0.1:8001 --engine-origin http://127.0.0.1:8010

The archive is capped at 32 GiB and the ordinary source inventory at one
million entries. Git archive export rules apply. Symlinks, special files,
private configuration and missing required build inputs fail closed. The
candidate workspace and successfully produced image IDs are preserved on
interruption. This builder does not establish reproducible dependencies,
sign images, use private registries or perform a hermetic build.

Independent review creates an approval JSON with exactly schema
(skeleton.application.first-install-image-approval.v1), source_head,
build_receipt_sha256 (SHA-256 of the original receipt file), authority_id,
project, review_evidence_sha256, issued_at and expires_at (integer Unix
seconds, validity at most one hour). Sign the canonical sorted compact
ASCII JSON prefixed by the bytes skeleton.first-install-image-approval.v1
followed by a NUL byte, using the independently pinned Ed25519 key.
The public key and signature are raw 32-byte and 64-byte files respectively,
not embedded in the plan. This script never produces the signature.

    python scripts/qualify_first_install_images.py --source-head REVIEWED_SHA prepare \
      --build-receipt /private/builds/review.json --plan /private/approval.json \
      --signature /private/approval.sig --public-key /private/authority.pub \
      --authority REVIEWER --project PROJECT --frontend-port 8080 \
      --output /private/reviewed-images.json

The resulting Compose override contains only approved isolated image tags
and pull_policy never. The operator must use the existing canonical
production mode ports and configuration, the exact approved project, and
--no-build with the override. No automatic container recreation is
performed by this tool. The observe mode takes the same approval inputs
without --output, and independently checks twice that all three running
image IDs, container identities, loopback publications, expected persistent
mounts, absence of source-shadowing mounts and canonical bridge ownership
match the reviewed build. Both strict live application health and actual
inference remain separate requirements. The receipt is not release or
Windows/WSL2 qualification. Independent build approval authenticates the
reviewed evidence, not an untrusted daemon or filesystem.



### Interrupted lifecycle operations

The installer, source CLI and Windows launcher share an OS-backed lifecycle
lease and write a bounded, non-secret intent before invoking Compose start,
stop or isolated setup-UI recovery. A signal, interrupted process, timeout,
OS error or invalid exit receipt leaves that intent in place. Ordinary
process completion clears only the matching intent. This is a local
cooperating-client safety boundary, not a Docker daemon lock or proof of
database consistency; Windows directory power-loss durability is not qualified.

Inspect the previous operation without dispatching a new Docker command:

```text
python -m skeleton app runtime-recovery status
SkeletonOffline.exe --runtime-recovery status
```

Check Docker Desktop or the selected Docker context and existing Compose
project, confirm that no previous operation is still running, and inspect
persistent data before acknowledging. The installed launcher also exposes
**Interrupted Operation** and **Acknowledge Recovery**. Use the exact ID
from the status receipt:

```text
python -m skeleton app runtime-recovery acknowledge OPERATION_ID --daemon-inspected
SkeletonOffline.exe --runtime-recovery acknowledge OPERATION_ID --daemon-inspected
```

Acknowledgment records an explicit operator decision; it does not verify
daemon idleness, retry startup, delete application data or certify readiness.
A malformed or mismatched intent is intentionally preserved for manual
investigation. Do not delete the lock or pending record to bypass custody.



### Persistent identity on reinstall

The installer and source setup command require a read-only selected-daemon
storage inventory before generating missing persistent database/signing/sealing
credentials. A deleted .env does not imply an empty Docker installation.
Canonical volume suffixes, Compose volume role labels and fixed application
container names are checked, including stopped containers; inventory changes
or unverified Docker output deny new identity. No volume is created, mounted,
deleted, inspected for contents or authenticated by this check. Existing
credentials are preserved; restore the original private configuration rather
than generating keys for old data. Explicit custom Mongo database paths,
replica-set and authentication options are not normalized into a standalone
bundled URI. This conservative policy may block another canonical stack in
the same Docker context; independent migration/backup qualification is still
required. Low-level offline configuration generation is not storage-qualified.


Inspect the selected daemon using the source CLI or installed console:

```text
python -m skeleton app storage-custody
SkeletonOffline.exe --storage-custody
```

The Windows launcher has a Storage Custody control exposing only canonical
role identities. Process-level overrides for persistent database, sealing
and signing identity must match the admitted private configuration; the
installer rejects mismatches before its configuration publication or
Compose startup. These are local installation rules; managed deployments
using a separate secret-injection contract must qualify separately.



### Resolved Compose storage binding

Before local startup, the installer and source CLI render the exact pinned
Compose model in private temporary capture. The resolved project, named
local-volume definitions and authoritative mount targets must match the
canonical storage roles. Existing fixed-name containers must have matching
Compose project/service labels and writable authoritative volume mounts.
Existing volumes must carry the matching project and role labels. Alternate
canonical volumes, mount substitutions, foreign containers and changing
inventory block startup rather than creating a new empty data plane. This
deliberately requires review of legacy unlabeled or relocated volumes.
No volume inspection includes database contents and no inspection runs a
Docker mutation. The transient rendered config may contain credentials;
it is not retained in the report. This is not secure erasure, database
authentication, backup verification or a daemon-wide transaction.


A successful Compose process exit triggers a second binding observation.
The selected daemon identity and resolved storage model must still match,
previously observed volume creation metadata must remain stable, and the
four required application containers must be running with canonical
bindings. Container and volume metadata are sampled twice per observation.
These are point-in-time metadata checks, not immutable volume identity,
data-content validation, or proof against arbitrary external Docker races.
The CLI --no-verify switch skips HTTP verification only, not storage custody.

The reviewed hot-reload distinction is explicit: the backend source bind
may cover /app only when the resolved model selects the local checkout's
backend directory read-only and retains a separate writable /app/data
volume. A previously running hot-reload backend can be replaced with a
production container while retaining the named data volume. This storage
exception does not attest the identity of code in an existing bind mount.


The same launch observation also checks all resolved host port mappings
against the selected local installation and mode. Post-start observations
compare each running service's actual TCP bindings and image ID to the
resolved service image reference and observed local image tag. Public or
unexpected port bindings and mismatched image tags deny readiness. A
per-campaign keyed fingerprint covers the entire resolved Compose model,
including build arguments and environment, without publishing secret-bearing
config or fingerprint data. This does not establish registry trust, build
provenance, image source parity, immutable volume identity or device readiness.

Positive HTTP and critical-router qualification is now followed by a final
read-only runtime continuity observation. Active container IDs, start
timestamps, restart counts, image identities and ingress bindings must
match the post-start observation. An observed restart or replacement
invalidates the earlier HTTP evidence. The stricter optional live
qualification gets the same final continuity check. This is sampled
continuity, not continuous monitoring or physical-device certification.


The App Foundation E2E stack now uses the shipping pre-start and post-start
binding observers in its isolated CI project. This is separate from
developer/consumer installation and only runs when the existing E2E job is
admitted; draft, queued or skipped jobs are not evidence. The strict source
qualification worker disables site startup and uses a new private bytecode
cache prefix, so a checkout's cached bytecode cannot replace tracked Python
source. Source and configuration are rechecked after inter-round delay
before the next HTTP round. Neither change supersedes physical qualification.


The real-Compose source contract also runs in the independent App Foundation
E2E companion job. It renders development, production, custom production
ports and the reviewed hot-reload overlay with disposable process-local
fixture credentials. The source check requires exact browser build/runtime
URLs, internal engine wiring, shared service credentials, Mongo inputs and
dependency health fences. It does not start containers, exercise the live
stack, or change the existing draft/live qualification admission rule.


Frontend-only recovery now reuses the original pinned Compose render and
prior daemon/storage identity after a failed full startup. It requires
the exact no-dependencies frontend command, reobserves the running
frontend image and ingress before probing /setup, and verifies that
frontend's runtime identity again after the probe. Protected startup
remains failed even if the diagnostic page answers. No Chroma migration
or automatic data repair is authorized.


Shutdown remains a non-destructive Compose stop including the legacy
Chroma profile. Source CLI and Windows launcher now share a shutdown
custody observer: identify the selected daemon and exact Compose project,
require fixed-name container ownership, and check that previously observed
container IDs and volume names still exist after stop. A successful exit
does not alone certify shutdown. This is sampled metadata continuity,
not backup or data-content validation. If project/configuration custody
cannot be established, inspect Docker Desktop directly rather than
removing persistent containers.


Whole-application HTTP readiness requires exactly one successful receipt
for each canonical frontend, backend, engine and aggregate application
endpoint (plus Chroma only for the separately requested full observation).
Each receipt must match the configured endpoint URL with an actual 2xx
integer status and an explicit success boolean. Partial or duplicate
inventory cannot finish a retry campaign or admit startup. Mongo has no
public HTTP health route; its custody and dependency health are separate.


Live status, smoke, Windows status and startup now retain a sticky
configuration epoch through health collection. If a source mutation is
observed, old receipts are discarded even if the file later contains the
original bytes. The installer captures setup's output before invoking
external phase observers, so an observer cannot substitute a new
configuration and have it accepted as the original setup result.


The local launch gate also checks the resolved and actual container isolation
settings. Backend and engine require a read-only root, non-root execution,
dropped capabilities, no-new-privileges and the bounded non-executable
temporary filesystem. Canonical services use a project-owned local bridge;
host namespaces, unreviewed device/capability grants and arbitrary host
bind mounts are rejected. The actual bridge ID is sampled through runtime
qualification, and Docker health must be healthy for Mongo, backend and
engine at the final HTTP continuity observation. These settings do not
attest host security, kernel integrity, registry trust or database contents.

Actual host-bind destinations and read/write permissions must also match
the reviewed model; arbitrary or writable model mounts cannot inherit the
model's positive observation. Actual VM host-source path identity is not
attested, because Docker Desktop can translate those paths. Conflicting
tmpfs safety flags, root user aliases and explicitly disabled default
security profiles are denied.


The semantic wiring gate now runs with the independent Compose isolation
contract on local installer startup, CLI startup, isolated frontend
recovery and real-Compose source CI. It validates exact resolved
credential propagation, private proxy bypass, local-only inference
identity, protected application authentication, browser build/runtime
origins, durable state paths, dependency health gates and canonical
build contexts before a mutation. Only fixed failure codes leave the
observer. This does not inspect running process credentials or prove
source-to-image provenance.
