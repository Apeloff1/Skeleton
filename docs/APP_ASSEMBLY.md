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
