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

# Validate/checkpoint identity and capacity without executing a model prompt:
python -m skeleton app local-ai --model ./native-runtime.json \
  --inspect-model --json

# Headless model inference with a bound JSON receipt, for scripts/automation:
python -m skeleton app local-ai --model ./native-runtime.json \\
  --prompt "hello" --max-output-tokens 8 --json

# From the Windows installer (no system Python required):
Skeleton.exe --local-ai
```

### Train a small native checkpoint on your own text

The desktop window's **Train small local model…** action can train a genuine,
small, causal transformer from an explicitly chosen UTF-8 text file using the
existing CPU training kernels, then reload and verify its native checkpoint.
No Docker, hosted API key, network, model download or external Python package
is required inside the bundled Windows executable. This is an **experimental
small model**, not a pretrained/production LLM; brief, low-quality outputs are
expected, and no general model-quality certification is made. It does not
perform unattended collection, training, promotion or overwrite weights.

```bash
python -m skeleton app local-ai --train-corpus ./notes.txt \
  --output-model ./my-native.json --epochs 1 --json
python -m skeleton app local-ai --model ./my-native.json --inspect-model --json
python -m skeleton app local-ai --model ./my-native.json \
  --prompt "user: hello" --max-output-tokens 8 --json
```

### Multi-category benchmark: reject localized regressions

Use **Evaluate…** in the native offline window, or use the headless suite
runner to test a checkpoint across several independent categories. Unlike a
single aggregate corpus score, a candidate fails the local regression gate
if **any** category becomes worse in predicted-token-weighted perplexity
(or if an optional next-token top-1 objective loses correct predictions),
even if overall perplexity improves.

Create a bounded `suite.json` using the exact native vocabulary in your
checkpoint. Cases must have distinct identities and distinct normalized token
sequences; case text is hashed and is not echoed in the report.

```json
{
  "schema": "skeleton.ai.offline.benchmark.v1",
  "cases": [
    {"id": "dialog-1", "category": "dialog", "text": "user hello assistant world"},
    {"id": "dialog-2", "category": "dialog", "text": "hello user world assistant"},
    {"id": "reason-1", "category": "reason", "text": "world alpha hello"},
    {"id": "reason-2", "category": "reason", "text": "hello alpha world"}
  ]
}
```

```bash
# Read-only benchmark for one checkpoint:
python -m skeleton app local-ai --benchmark-suite ./suite.json \
  --model ./my-native.json --json

# Protected-category acceptance (exit 0 = local nonregression, 1 = rejected):
python -m skeleton app local-ai --benchmark-suite ./suite.json \
  --model ./my-native.json --candidate-model ./my-native-v2.json --json
```

To test against an explicitly known training corpus, supply
`--exclude-train-corpus ./train.txt`. The benchmark fails closed when a
case is identical to a training line after tokenization or copied as a
contiguous multi-token fragment. The receipt includes the training-source
digest without echoing the raw training text. The check cannot prove
disjointness from unknown, historical, third-party or otherwise unavailable
training data.

The suite is limited to 64 cases, 16 categories, 128 KiB and 1024 total
tokens, with strict duplicate-key / non-finite / symlink rejection. Every case
is evaluated against the same verified tokenizer identity and its metrics
carry the suite/content hashes; no release state is modified. Category
results are diagnostics, **not** independent certification of safety or
general model performance. The optional `expected_next` case field
can evaluate top-1 accuracy for a token from the exact checkpoint vocabulary.

### Continue improving existing weights, with rollback

The **Improve model…** button and CLI can continue local CPU training of
an existing native checkpoint and measure held-out perplexity on a distinct,
explicitly supplied UTF-8 file. Both corpora must use the existing vocabulary;
unknown words and exact overlapping training/evaluation lines fail closed.
The source checkpoint is never modified. A new candidate checkpoint is written
**only if** at least one trained epoch lowers held-out perplexity versus the
original. The best measured epoch is selected; all regressions reject the
candidate with no output file. This is a bounded local improvement trial,
**not** evidence of generalized intelligence or a production-model promotion.

```bash
python -m skeleton app local-ai --improve-model ./my-native.json \
  --train-corpus ./train.txt --eval-corpus ./heldout.txt \
  --output-model ./my-native-v2.json --epochs 3 --json

# Optional stricter training: require a THIRD, independent benchmark
# suite (disjoint from training and held-out epoch-selection text).
python -m skeleton app local-ai --improve-model ./my-native.json \
  --train-corpus ./train.txt --eval-corpus ./heldout.txt \
  --protect-suite ./protected-suite.json \
  --output-model ./my-native-v2-protected.json --epochs 3 --json
```

After saving a candidate, run a **read-only comparative evaluation** using the
same separate held-out file. This returns exit code 0 only when the candidate
beats the parent on bounded token perplexity, and exit code 1 on a regression.
It does not change either checkpoint or grant release-promotion authority.

```bash
python -m skeleton app local-ai --compare-model ./my-native.json \
  --candidate-model ./my-native-v2.json \
  --eval-corpus ./heldout.txt --json
```

Both model identities and tokenizer consistency are verified before scoring;
the receipt records validation source identity, measured perplexity for both
models, and the Boolean result. If you edit the validation source, the digest
changes and previous scores cannot be silently treated as comparable.

### Reproduce a learned checkpoint from its source evidence

A local candidate can be independently **recomputed** without touching its
existing parent or candidate checkpoint. Save the original improvement CLI
output to a JSON file, then invoke the deterministic replay verifier:

```bash
python -m skeleton app local-ai --improve-model ./my-native.json \
  --train-corpus ./train.txt --eval-corpus ./heldout.txt \
  --output-model ./my-native-v2.json --epochs 3 --json > accepted-receipt.json

python -m skeleton app local-ai --replay-improvement ./accepted-receipt.json \
  --compare-model ./my-native.json --candidate-model ./my-native-v2.json \
  --train-corpus ./train.txt --eval-corpus ./heldout.txt --json
```

For a protected improvement, also supply the original `--protect-suite`
file during both generation and replay. Replay strictly validates the receipt
JSON, all four artifact/data identities, training and validation metrics, and
the optional protected suite. It then **re-trains actual CPU weights** into
temporary storage and verifies that the resulting checkpoint has the exact
same digest. The scratch data is deleted afterward. Edited sources, mismatched
weights, corrupt receipts or nonreproducible floating-point behavior fail
closed, without modifying either input checkpoint.

The receipt is a content-addressed local record, **not** a signed identity or
third-party audit. Matching a tiny native checkpoint is not an independent
production-model quality, safety or general intelligence certification.

The JSON receipt binds the original/candidate model digests, tokenizer identity,
both source digests, original/new artifact hashes, CPU training steps, best epoch,
and baseline/accepted held-out perplexity. Keep the input artifact to roll back.
No remote provider, autonomous data harvesting, hidden training, or destructive
overwrite is permitted. Held-out fit is a **narrow** metric and not independently
certified safety, reliability or broad intelligence.

Training is bounded to a 32-KiB input file, at most 512 normalized tokens,
256 vocabulary entries, and 1–4 CPU epochs with a fixed small architecture.
The output is checkpointed using the existing model artifact writer, loaded
again and verified against the trained native model digest. A path that
already exists is refused rather than overwriting previous weights.

Use **Load checkpoint…** to open a `write_local_model_artifact`-compatible
native transformer JSON artifact. File size, duplicate keys, SHA-based model
identity, runtime/tokenizer graph, and all checkpoint fields are validated by
the canonical artifact and native runtime owners before inference. The
window carries conversational context within the model's finite token budget,
drops only oldest *full* turns when required, offers generation cancellation,
and only commits a turn to its session history after the local inference
receipt is complete. No tools, providers or network transport are granted by
this window. The local transcript stays in memory by default. **Open chat…** and **Save chat…**
support explicit, private, model/tokenizer-bound JSON snapshots: the file
contains readable plaintext conversation, has a SHA-256 corruption check
(not a cryptographic signature), rejects symlinks/oversized or malformed
inputs, and is atomically replaced on save. The user chooses when and where to
save it; no cloud upload, background autosave, extra runtime service or
provider credentials are involved. A transcript can only be imported when
the exact checkpoint and tokenizer identities match. It is a portable
non-authoritative projection, **not** the governed assistant's persistent
transactional conversation state.

```bash
python -m skeleton app local-ai --model ./native-runtime.json \
  --prompt "Hello" --max-output-tokens 8 --save-chat ./chat.json --json
python -m skeleton app local-ai --model ./native-runtime.json \
  --prompt "Continue" --max-output-tokens 8 \
  --load-chat ./chat.json --save-chat ./chat.json --json
```

The canonical governed assistant/workspace remains the durable product authority.

**Scope:** this is an independently usable local desktop execution surface,
not a claim that the complete product shell, all 421 masterplan volumes, advanced
model quality, multimodal inference, autonomous learning, native weights,
security qualification or installation acceptance are finished. Docker is
still required by the existing full frontend/backend/Mongo service profile.
Windows `Skeleton.exe`/Inno Setup must still be built and smoke-tested on a
Windows runner before this mode can be described as shipped.

Targeted source validation:

```bash
python -m unittest tests.flgb.test_desktop_offline_ai tests.flgb.test_offline_chat_transcript tests.flgb.test_offline_native_training -v
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
- `setup` creates or repairs `.env` atomically. It generates local Mongo and
  JWT secrets when required, preserves valid existing values, never prints
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
