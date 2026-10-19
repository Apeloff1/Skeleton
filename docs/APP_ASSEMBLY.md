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
A normal `app down` retains
application and database volumes. Ordinary startup failures do not require
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
