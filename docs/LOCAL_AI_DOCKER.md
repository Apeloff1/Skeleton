# Skeleton Local AI Docker: operator system and acceptance gates

Status: **source implementation; not a qualified release**. This is an **opt-in
Compose overlay** on the canonical Skeleton application, not a new independent
inference provider, a network model downloader, or an assertion of hardware
qualification. The architecture contract deliberately retains the five canonical
services: `frontend`, `backend`, `skeleton`, `mongo`, optional `chroma`.

**Critical existing product gap:** the canonical guarded local chat provider
still cannot activate under the default Compose bootstrap. The engine currently
lacks a trusted `ProtectedLocalComponents` composition, a GGUF-bound tokenizer
attestation, a shared majority-durable epoch across backend conversation and
engine memory writers, and an independently operated reviewer. The existing
standalone Mongo configuration also lacks the replica-set linearizable epoch
read guarantees. See
`docs/qa/GUARDED_LOCAL_READINESS_2026-10-28.md` and the first-install warning
in `README.md`. A real `llama.cpp` one-shot response **does not** close those
gaps. The host `up` command now treats missing canonical provider readiness as
an ERROR even when containers are healthy; services may remain running for
diagnosis. There is no fallback that disables the guard.

## Purpose and gap closure

The base `docker-compose.yml` already runs the API, backend, frontend,
authenticated MongoDB and optional Chroma. It mounts
`SKELETON_LOCAL_MODEL_DIR` read-only into `/app/local-ai`, and the engine already
supports a pinned `llama.cpp-cli` GGUF deployment through
`skeleton.ai.runtime.inference.deployment.LocalModelDeployment`. That alone does
**not** provide an operator-visible container lifecycle for Jeeves. Previously
there was no explicit CPU/CUDA/ROCm Compose selection, no Docker-side create-only
model binding workflow, no isolated launch qualification, no resource-tuned
local-AI overlay and no single guarded operator sequence.

This deployment keeps **one model owner**: `skeleton/provider_runtime.py` activates
the existing guarded local provider; the standalone one-shot tooling invokes
the exact existing `create_local_model_deployment` and
`qualify_local_model_deployment_sync` contracts. It neither introduces a new
provider boundary nor imports an external hosted model SDK.

## Files and ownership

| Path | Authority |
| --- | --- |
| `docker-compose.yml` | Canonical base and persistent state mounts; unchanged |
| `docker-compose.local-ai.yml` | Opt-in engine-only local AI and resource controls |
| `docker-compose.local-ai.nvidia.yml` | NVIDIA GPU reservation only, applied after local |
| `docker-compose.local-ai.rocm.yml` | Linux AMD render devices only, applied after local |
| `scripts/local_ai_docker.py` | Host operator: inspect, build, pin, qualify, up, status, stop |
| `skeleton/app/docker_local_ai.py` | Container-side canonical pin and real inference probe |
| `skeleton/testing/test_docker_local_ai.py` | Focused denial, mounting, provider and command tests |
| `deploy/local-ai/local-ai.env.example` | Non-secret resource tuning template |

The application still owns durable sessions, receipts, workspace, governance,
admission and data state through its existing MongoDB, SQLite and data-volume
authority. Model weights and executable libraries are **operator-owned** and
never copied into the engine image. Their bind mount is read-only in normal
service operation.

## Supported deployment classes

| Class | Container requirements | Model/runtime artifact | Qualification status |
| --- | --- | --- | --- |
| CPU / x86-64 Linux | Docker Engine or Docker Desktop Linux containers | Linux-glibc llama.cpp binary, GGUF, pinned library set | Runnable after actual local probe |
| NVIDIA CUDA / Linux | Host driver and NVIDIA Container Toolkit, Compose GPU reservation | Compatible CUDA-enabled llama.cpp binary and pinned shared libs | Device request only until physical trace proves offload |
| NVIDIA / Windows 11 WSL2 | Docker Desktop WSL2 Linux backend, NVIDIA WSL-capable driver and GPU support | Linux CUDA binary, not a Windows EXE | Requires real Windows/WSL2 device acceptance |
| AMD ROCm / supported Linux | `/dev/kfd`, `/dev/dri`, authorized render GID | Matching ROCm llama.cpp binary and libs | Requires real AMD device acceptance |
| macOS Apple Silicon | Docker Linux VM does **not** expose host Metal as a native Linux GPU | CPU Linux executable | Use native Metal runtime outside Docker for Metal acceleration |
| CPU / ARM64 Linux | ARM64-compatible Linux binary, GGUF, platform-compatible image | No pinned cross-architecture installer artifact assumed | Requires ARM64 artifact and native device proof |

These are **platform paths**, not claims that every machine is qualified.
CUDA/ROCm offload must not be inferred from a GPU container flag, a successful
text response or a CPU fallback. The manifest's `gpu_layers` is a *request*.
Hardware identity, effective offloaded layers, VRAM/RAM accounting, driver ABI
and a physical successful inference trace are separate release evidence.

## Preparation: existing install and model supply

1. Clone or update the repository into a **private** working tree with enough
   disk space for the Docker images, a GGUF, libraries and durable volumes.
2. Install Docker Engine with the Compose v2 plugin (or Docker Desktop Linux
   containers on Windows 11/WSL2). On NVIDIA hosts install and verify the
   appropriate NVIDIA Container Toolkit. On AMD hosts verify the device files
   and render-group permission without using `privileged: true`.
3. Run the canonical application setup to create the private `.env` with
   authenticated Mongo URLs and generated application/engine secrets:
   `python -m skeleton app setup`. Do not commit or paste `.env`.
4. Create the operator-owned `data/local-ai` directory (or the explicitly
   configured `SKELETON_LOCAL_MODEL_DIR`) and supply an existing **licensed**
   GGUF, a matching Linux executable and any dependent shared libraries.
   Runtime files must be actual files: no symlinks, no git LFS pointers, no
   Windows PE executables in Linux containers.
5. The engine container uses uid/gid `10001:10001`. The one-shot `pin`
   operation needs that user to be able to create `jeeves.json` in the model
   directory. Grant only the narrow required write permission while pinning;
   the normal service bind is always read-only.

Skeleton already contains an explicitly opt-in, SHA-pinned x86-64 CPU supply
recipe: `python scripts/provision_local_ai.py --help`. Its downloads are not
invoked by Docker and require the operator's explicit `--download`. Any user
supplied GPU build must be independently custody-pinned; never treat the CPU
release digest as proof of a GPU binary. A production deployment also requires
a reviewed base image and artifact/license chain.

## CPU: build, bind, qualify, run

Commands below assume root `.env` exists and the base model mount is present.
The host script **never** executes `docker compose down`, removes or prunes
volumes, changes stored model weights or installs a hosted model.

```bash
# 1. Inspect rendered Compose with secrets kept out of printed diagnostics.
python scripts/local_ai_docker.py --mode cpu doctor

# 2. Build the canonical Skeleton engine image, not a second AI server.
python scripts/local_ai_docker.py --mode cpu build

# 3. Create ONE immutable Jeeves deployment in /app/local-ai/jeeves.json.
# Both paths below are relative to the mounted operator model directory.
python scripts/local_ai_docker.py --mode cpu pin \
  --model models/your-licensed-model.gguf \
  --executable runtime/llama-completion \
  --profile qwen3-completion-chat \
  --context 4096 --threads 4 --gpu-layers 0

# 4. Verify exact digest pins and actual inference. Both use --network none.
python scripts/local_ai_docker.py --mode cpu preflight
python scripts/local_ai_docker.py --mode cpu qualify

# 5. Attempt application startup (up never builds or downloads models).
# EXPECT a fail-closed readiness error until the canonical protected
# bootstrap/Mongo epoch/tokenizer prerequisites are implemented and qualified.
python scripts/local_ai_docker.py --mode cpu up
python scripts/local_ai_docker.py --mode cpu status

# Stop without destroying containers, volumes, or Chroma recovery material.
python scripts/local_ai_docker.py --mode cpu stop
```

Choose a profile that actually matches the model's chat template: Qwen3-only
for compatible Qwen3 completions, `llama-completion-chat` for a compatible
completion chat model, or `raw` when the operator has verified the prompt
contract. Changing a profile, model, executable, context or GPU layer count
requires a **new, deliberate create-only model pin** and a rollback snapshot.
Do not edit the JSON in place to silently change previously admitted identity.

`pin` runs a one-shot container with `--network none` and a *temporary
writable* model mount, then uses the canonical create-only digest-binding
function. `preflight` reloads and verifies executable/weight digests and the
container-root paths. `qualify` executes the actual GGUF model through the
canonical inference engine and returns a model/runtime/manifest-bound receipt
without revealing prompt or response text. The host operator now validates the
exact phase-specific JSON schema, single Jeeves identity, local-only and
network-disabled booleans, three SHA-256 identities, receipt content digest,
and runtime/model-bound response identity. A subprocess returning exit code 0
with arbitrary text is denied. The engine source is unchanged; these checks
only prevent false-positive Docker startup qualification. A swapped model or
runtime between the two one-shot checks refuses service startup. Only after these succeed does
`up` attempt the application to start. It then queries the **actual**
`/api/ai/providers` projection from the canonical backend and errors if
local Jeeves readiness was not positively observed. The live engine continues
to run its own guarded provider activation and is currently expected to
report `local_guard_unavailable` until separately repaired. Service
containers are retained for investigation if this check fails; they are not
automatically deleted or rolled back.

The normal engine container runs non-root, drops all capabilities, sets
no-new-privileges, has a read-only root filesystem, a bounded tmpfs,
`init` child reaping, a bounded pids quota, CPU/RAM/shm limits and a
read-only model mount. Backend/engine credentials remain from application
setup, not baked into images.

## NVIDIA: explicit GPU selection

```bash
python scripts/local_ai_docker.py --mode nvidia doctor
python scripts/local_ai_docker.py --mode nvidia build
python scripts/local_ai_docker.py --mode nvidia pin \
  --model models/cuda-approved.gguf \
  --executable runtime/llama-completion \
  --context 4096 --threads 4 --gpu-layers 24
python scripts/local_ai_docker.py --mode nvidia qualify
python scripts/local_ai_docker.py --mode nvidia up
```

The selected `nvidia` overlay reserves **one** GPU using Docker Compose
device reservations. It does **not** add `privileged`, access to the host
Docker socket or broad system mounts. A container image must have compatible
CUDA userspace libraries, supplied and pinned with the runtime. Confirm
`nvidia-smi` host visibility; for Windows 11, confirm the Linux container can
see the GPU through WSL2. Qualify real GPU kernel execution and VRAM telemetry
before calling this physically GPU-qualified. If GPU libraries are absent, fail
or report unqualified rather than silently describing CPU execution as CUDA.

## AMD ROCm: supported Linux hosts only

```bash
# Use your real authorized host render group GID, not a guess.
export SKL_LOCAL_AI_RENDER_GID="$(getent group render | cut -d: -f3)"
python scripts/local_ai_docker.py --mode rocm doctor
python scripts/local_ai_docker.py --mode rocm build
python scripts/local_ai_docker.py --mode rocm pin \
  --model models/rocm-approved.gguf \
  --executable runtime/llama-completion \
  --context 4096 --gpu-layers 24
python scripts/local_ai_docker.py --mode rocm qualify
python scripts/local_ai_docker.py --mode rocm up
```

The container requests only `/dev/kfd`, `/dev/dri`, and the explicitly
authorized numeric group. The host is responsible for driver, kernel, ROCm
userspace, model and runtime compatibility. On distributions without this
device/permission layout, the mode is unavailable; do not disable seccomp
or add blanket privilege to make an unqualified host appear green.

## Resource sizing and admission

Start with **one** concurrent local text generation. The default overlay
uses an 8 GiB engine memory limit, 4 CPUs, 256 MiB shared memory, 512 process
IDs, a queue ceiling of 8 and a batch ceiling of 8. These are conservative
**operator configuration defaults**, not promises about model fit or speed.

Before increasing context, batch or concurrency:

- Include weight mapping, KV cache geometry, prefill buffers, pinned runtime
  shared libraries, Python engine overhead, GPU/CPU intermediate tensors and
  concurrent operations in the budget. GGUF file bytes alone do not bound
  peak memory use.
- Use `python scripts/plan_consumer_gguf.py --help` for conservative
  geometry-aware RAM planning, then confirm with hardware measurements.
- For Docker Desktop/WSL2, account for the Docker VM's own RAM/swap quota,
  not just physical host RAM. Exceeding the cgroup limit can OOM-kill the
  engine and should leave backend inference unavailable, not fall back to
  hosted AI.
- Increase `SKL_LOCAL_AI_MEMORY`, `SKL_LOCAL_AI_CPUS` and the local
  admission variables in private `.env` together with observed headroom.
  `SKL_LOCAL_AI_CONCURRENCY` must not exceed real model/VRAM capacity.
- Rotating or rolling a model while active requests are in flight is not
  implemented by changing its manifest. Drain and stop; retain the original
  pin and files for exact rollback.

The canonical local inference engine already owns bounded admission,
cancellation, model identity and guarded provider activation. Do not add a
second independent queue, vector database or OpenAI-compatible server and
silently redirect Jeeves to it.

## Security boundaries and limitations

- **Inference** is local-only: `AI_PROVIDER=local`,
  `JEEVES_LOCAL_ONLY=1`, `AI_LOCAL_GUARD_REQUIRED=1`; single deployment
  `/app/local-ai/jeeves.json`; no secondary verifier or hosted credentials
  in the engine environment. The host doctor checks the fully rendered
  Compose config, not just the overlay source.
- **One-shot pin/qualification** uses `docker run --network none`. Docker
  still needs network access when building/pulling dependencies; model weights
  are never downloaded by these commands.
- **Running service network** is **not airgapped**: it requires the existing
  internal Mongo and backend network and is not made outbound-isolated by
  `JEEVES_LOCAL_ONLY`. Enforce network-deny policy using reviewed host
  firewall/egress rules if the whole application must be offline. This
  deployment does not assert complete offline security or external API
  isolation for unrelated backend features.
- **Credentials**: retain canonical secret setup, do not print rendered
  Compose JSON (it contains secret environment values), never store tokens
  in model manifests, image layers or receipts.
- **No risky cleanup**: do not use `docker compose down -v`,
  `docker volume prune`, `docker system prune` or `--remove-orphans`.
  The optional Chroma image has a documented persistence path mismatch;
  preserve its existing container and writable-layer `/data` until a
  separately verified migration is complete. See `docs/APP_ASSEMBLY.md`.
- **Read-only model custody**: runtime files are read-only to the engine,
  but an operator with host directory access can replace them. Activation
  and actual generation must recheck digest identity. An SHA proves bytes,
  not license, model quality, safety or supply-chain origin.
- **No privileged tool execution**: a model response is not authorization
  to run shell tools, alter source, train itself or access arbitrary host data.
  Existing Skeleton tool/governance policy remains in force.

## Persistence, migration and rollback

Model bytes and runtime binaries live in the host's
`SKELETON_LOCAL_MODEL_DIR`; internal operation records and conversation state
remain in existing named volumes. Model artifacts are **not** recreated from
Compose or backed up by backing up only Mongo. Maintain a separate offline
copy of `jeeves.json`, exact executable, all pinned runtime shared libraries,
GGUF files, license/provenance documentation and SHA-256 inventory.

Before a model change: stop accepting AI requests, snapshot the model directory
and application-authoritative volumes consistently, record exact head commit,
container image identity, manifest/executable/model SHA and the resource
profile. Create a **new** manifest in a new operator-owned versioned model
directory; never mutate a pinned manifest in place. Change only the
read-only model mount root in private configuration during planned cutover,
requalify in a new one-shot container and then recreate the engine with
`docker compose up` as a deliberate service event. If a new model fails,
stop the engine, restore the prior directory pointer and prior image,
validate pins and startup guards, and verify application state independently.

For the authoritative Mongo store, preserve consistent backup snapshots
with database-specific tools. For SQLite, include journals and verify an
offline consistent snapshot. Chroma is a *separate recovery hold*, and the
current bind path must not be assumed durable. Full recovery means the UI,
backend, engine, model and each authoritative store all pass their own
verification, plus preserved session/workspace identities after restart.

## Acceptance matrix: do not confuse levels

1. **Source validation**: Python byte compilation, focused unit tests,
   YAML parsing, canonical architecture and provider checks.
2. **Compose topology**: `python scripts/local_ai_docker.py --mode cpu doctor`
   and `docker compose ... config --format json`; only the canonical
   five services may exist, with local guards and read-only mounts.
3. **Artifact identity**: `preflight` verifies exact weight and runtime digests.
   Preflight is not proof that the model can generate.
4. **Actual local inference**: `qualify` performs a real subprocess turn
   with the network disabled and emits a digest-bound receipt. Fake/mock text
   cannot satisfy this gate.
5. **Application integration**: run `up`; validate engine/backend/frontend
   health, guarded provider activation, authenticated chat turn, durable
   session ownership and no hosted fallback. Test model-absent, corrupt,
   model-binary mismatch, low-RAM, timeout, cancellation and OOM recovery.
6. **Device qualification**: CPU timing and memory under load; NVIDIA or
   ROCm GPU kernels and offload telemetry on the actual machine; Windows
   11/WSL2 Docker Desktop; recovery after service restart.
7. **Release qualification**: exact-head CI, security scanning, frozen
   container artifact provenance, native/device/Windows evidence, migration
   rehearsals, and separately authorized merge and release.

Suggested focused source commands, run **after** implementation:

```bash
python -m compileall -q skeleton/app/docker_local_ai.py scripts/local_ai_docker.py
python -m pytest -q skeleton/testing/test_docker_local_ai.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Actual Docker/GPU/device acceptance cannot be certified by source tests,
PR metadata, successful `docker compose config` or mocked inference. These
require an installed daemon, approved real weights and the target hardware.

The draft-safe Backend Quality workflow also executes the local Docker
source denial suite on each exact PR head. The host contract separately
rejects malformed or synthetic qualification receipts and tests that
`docker compose up` is never reached on failed pin/qualification or
a changed model digest. Tests run without a Docker daemon and do not
constitute physical inference evidence.

Synthetic credential-form Mongo URI fixtures in older deployment unit tests
have been broken into explicit source string concatenations without changing
their runtime values. The repository-native credential scanner is **not**
weakened; it must continue to reject actual committed credential-looking URIs.
Frontend CI command aliases are explicitly wired to existing custody tests
instead of bypassing frozen-upstream `node-forge` verification.

## Remaining explicit blockers

The work above delivers a source-level Docker deployment/operator layer.
**The full end-user local Jeeves chat gap remains open.** Its next source
repair must introduce and qualify a declared shared majority-durable Mongo
writer epoch and migration (across the existing backend and engine databases),
an independently administered reviewer, a backend-exact GGUF tokenizer
attestation, and trusted `create_app(trusted_protected_bootstrap=...)`
composition without adding a provider owner or weakening any guard. Migration
must preserve existing Mongo data and canonical writer custody. The existing
standalone Mongo service and test-only in-process writer inventory cannot
supply that evidence.

This change does **not** claim a full production release, automatic CUDA/ROCm
binary supply, physical GPU qualification, an airgapped application network,
complete offline installer packaging, tested backup restores, or model
benchmark superiority. None of those gates should be marked green until
independent exact-head receipts exist.
\n### Source-custody lexer and receipt envelope repairs\n\nThe provider bootstrap Dockerfile source-custody parser now rejects unsupported,\nmultiple, partially matched or unterminated heredoc delimiters. A `FROM` or\n`COPY` embedded in such a script never certifies a new runtime layer or\npackaged source. This is tested against real backend Dockerfile stages and\nadversarial injected statements. The local-AI operator also checks the actual\ncanonical GGUF receipt SHA-256 over the engine payload **without** the external\nCLI `ok` envelope. This is essential: including `ok` in the digest would\nreject every genuine inference receipt even when real inference succeeded.\n
### Actual backend readiness projection

The runtime operator now checks the actual `backend/routes/ai.py` JSON payload:
`providers` contains **objects** with `id`, `model`, `available` and
`ownership`, not a list of provider-name strings. The guarded local-readiness
check requires one engine-owned local Jeeves row, the active local provider,
positive backend observation and positive local availability. Negative fixtures
cover remote providers, missing/duplicate local entries, mismatched models,
false observation and unavailable local inference. This does **not** substitute
for a successful authenticated chat turn, durable multi-writer epoch or actual
physical GPU evidence.

### Frontend dependency byte custody (integration unblocker)

The first-install Docker/frontend CI path must never mutate the reviewed
`node-forge` 1.4.3 RSA verifier. The postinstall hook now invokes the existing
SHA-256-pinned `verifyReviewedForgeRsa` helper without writing any RSA bytes.
Unrecognized versions, changed files, hardlinks, symlinks and altered source
fail closed. The original node-forge pin and release-time hostile RSA signature
probe are retained. The explicit `test:node-forge-custody` command executes
exact installed-byte verification and immutable-postinstall denial tests; this
is source/integrity evidence only, not full frontend export or release approval.

### Image dependency profile separation

The canonical Dockerfile retains its existing default dependency graph for
ordinary application installation. When launched through the local-AI overlay,
`SKL_LOCAL_ONLY_IMAGE=1` excludes the optional `hosted-inference` extra from
the image dependency install plan while retaining baseline application and
`local-inference` packages. The host doctor rejects a rendered Compose image
where this build argument is absent or disabled. This reduces optional hosted
SDK attack surface; it does **not** assert that transitive dependencies can
never contain HTTP clients, nor that the application network is air-gapped.

### Real Docker Compose parser validation in CI

The source-only `scripts/qualify_local_ai_compose.py` invokes the actual
`docker compose config --format json` parser for CPU, NVIDIA and ROCm
with ephemeral generated synthetic credentials and a temporary model-mount
path. It never prints the sensitive Compose JSON, contacts a Docker daemon,
pulls an image, downloads weights, or claims physical accelerator execution.
It rejects provider-fence drift, missing mandatory services, unexpected new
services, unsafe mounts, missing local-only image build args, resource limits
and missing GPU profile requests. Chroma may be absent when its optional
Compose profile is inactive. The launch path uses bounded Compose `--wait`
health admission before the existing backend provider readiness check; it
still does not authorize real chat without the trusted model guard.
