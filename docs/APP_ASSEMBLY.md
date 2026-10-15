# Application Assembly

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
```

The installer does not silently install Docker or elevate privileges. Missing
host dependencies fail closed with a remediation message. Setup writes only to
the ignored local `.env` file; installer receipts contain key names and phase
status, never generated secret values.

Older installations with a missing, placeholder or invalid-length
`SKL_ENGINE_SERVICE_TOKEN` are repaired by rerunning `app setup`. Runtime
preflight requires a normalized token of 32–4096 characters, matching the
engine client contract. Both services receive the same generated value from
Compose. After explicitly rotating secrets, restart backend and engine together
so their authentication values agree. Secret rotation also changes local Mongo
credentials; existing databases require coordinated credential migration.
Keep the previous private environment backup for rollback; never attach it to
diagnostic reports. Setup alone does not install trained AI weights or prove
model readiness.

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

# Include optional Chroma
python -m skeleton app up --full

# Inspect / operate
python -m skeleton app ps
python -m skeleton app smoke
python -m skeleton app logs backend
python -m skeleton app logs -f
python -m skeleton app config
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

## Frontend endpoint boundary

`frontend/utils/apiBase.ts` is the single endpoint resolver for browser and
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
