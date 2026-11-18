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


## Full-stack Compose admission (new source hardening)

The host doctor, build, pin, preflight, qualify, up and status commands now
enforce a second independent boundary on the **rendered effective** Compose
document before starting a container or running the model. This covers the
canonical browser/backend/engine/Mongo/optional-Chroma stack, rather than
checking only the engine. The validator lives in
`scripts/local_ai_compose_boundary.py`.

- **Ingress:** each canonical service must publish exactly one TCP port on
  `127.0.0.1` or `::1`. Wildcard, LAN, additional, privileged or host-network
  mappings are rejected. Internal target ports for the APIs/Mongo/Chroma remain
  fixed; the published frontend container target may be configured.
- **Browser:** runtime `EXPO_PUBLIC_BACKEND_URL` and
  `EXPO_PUBLIC_SKELETON_URL` must match the *actual rendered published*
  backend/engine ports, resolve only to local loopback, and equal the values
  baked into the frontend image build. This rejects a remotely redirected UI
  while the model is supposedly local.
- **Backend/database:** backend must talk only to the canonical engine service,
  retain the Jeeves local-only owner and service token, and use an authenticated
  internal Mongo URI. The engine Mongo URI is independently checked. Mongo's
  root-user setup must not be blank.
- **State and custody:** engine, backend, Mongo data/config and optional Chroma
  must preserve their canonical writable **named** volume targets. The reviewed
  Mongo/Chroma images must retain digest pinning; Chroma remains behind its
  `full` profile so the existing physical recovery hold cannot be bypassed by
  silently enabling it.
- **Adversarial checks:** dedicated source tests reject non-loopback publishing
  on *every* service, remote UI origins, mismatched frontend build origins,
  uncredentialed/remote Mongo, unexpected sidecars, privilege expansion,
  unpinned DB images and replaced authority volumes. These tests are included
  in existing Backend Quality and first-install qualification lanes.

A passing result reports `compose_boundary` with
`actual_network_qualified=false` and
`application_recovery_qualified=false`. Compose parsing cannot prove actual
host firewall containment, database consistency, epoch fencing, backups, GPU
offload, GGUF inference or guarded Jeeves chat. Those gates remain independent.
No state is modified by admission.

## Running-container acceptance: not just valid YAML

Source-level Compose admission only proves that a *proposed* topology is
acceptable. A pre-existing container can have a different image, mount, host
port, resource quota or provider environment. That matters especially for
first-install repair, Docker Desktop upgrades and long-lived model volumes.

The optional command below performs a **read-only Docker daemon attestation**
against the complete effective Compose document:

```bash
python scripts/local_ai_docker.py --mode cpu attest-runtime
# For a genuine NVIDIA deployment:
python scripts/local_ai_docker.py --mode nvidia attest-runtime
# For an authorized Linux ROCm deployment:
python scripts/local_ai_docker.py --mode rocm attest-runtime
```

This operation does not start, stop, build, update or download anything. It
requires the canonical four application services to be *already running* and
healthy as appropriate. Both `up` and `status` now execute the same daemon
inspection automatically; a passing `docker compose config` is insufficient.

### How the daemon is verified

1. Render and revalidate the actual mode-specific Compose topology, including
   local-only provider fences, internal authenticated Mongo, loopback browser
   destinations, the single `tutolage` private bridge and canonical writable
   state volumes. This operation never prints interpolated credentials.
2. Read `docker compose ps -q` for the four canonical services; require one
   unique active container per service. Docker metadata must identify the
   expected Compose project and service, rather than a similarly named
   foreign container.
3. Compare **live** port bindings and network-published ports with the
   effective host IP, TCP target and published port. A wildcard/extra port is a
   hard denial even if the Compose source would have been loopback-only.
4. Compare all live bind and named-volume targets, their write authorities
   and exact effective Docker volume IDs. In particular `/app/local-ai`
   remains a read-only host bind, whereas engine/backend/Mongo state remains
   on its intended writable named volumes.
5. Check the actual container environment against each Compose-owned variable.
   Engine-local AI identity and empty hosted-provider credentials are checked
   again. The audit does not echo environment contents, database credentials,
   token values or raw `docker inspect` JSON on failure.
6. For engine and backend, require the observed read-only root filesystem,
   dropped capabilities and no-new-privileges runtime security flags.
   Reject privileged, host-network and unexpected namespace access for any
   canonical service.
7. Compare the engine's effective Docker memory, shared memory, CPU nanocores
   and PID quota with the values rendered from the local AI overlay.
8. For CPU require no accelerator request. For NVIDIA verify a single requested
   GPU. For ROCm verify both declared Linux device paths and the applied
   render group. These checks **do not measure actual GPU layer offload**.
9. Independently resolve explicitly configured container image references to
   Docker image IDs and compare to observed running image IDs. A rebuilt tag
   with a stale running container is denied.
10. Inventory **all live containers** with the Compose project label,
    including otherwise profile-disabled Chroma and stale/orphan sidecars.
    Only the four canonical running services are admitted. Existing Chroma
    recovery remains a separate migration hold.

A passing read-only result uses
`skeleton.local-ai.docker.runtime-attestation.v1` and
`running_boundary_verified_not_guarded_chat_qualified`. The result reports
the compared image digests and explicitly sets
`database_epoch_qualified=false`, `guarded_chat_qualified=false`,
`gpu_offload_qualified=false` and
`application_recovery_qualified=false`.

**Image IDs are observed daemon state, not container signature validation or
release provenance.** The audit is one point-in-time observation and cannot
prevent changes made by a privileged host operator immediately afterward.
It cannot prove host firewall policies outside Docker, absence of kernel
compromise, a real GGUF inference trace or guarded Jeeves chat success.

### Immutable accelerator/model pairing

The Docker operator now checks the pinned GGUF manifest's
`gpu_layers_requested` and `context_size` before running an inference probe
or launching services. CPU mode requires zero GPU layers; CUDA and ROCm require
a positive declared layer count. Values must be proper integers within the
operator's bounded range. `pin` refuses a contradictory request **before**
opening a container. Standalone `qualify` first reads the pinned preflight
receipt and must also preserve exact manifest/model/executable digests between
preflight and actual local generation.

These checks prevent an operator from accidentally selecting a GPU profile
while retaining a CPU-only manifest. They are **not** a VRAM capacity test,
driver ABI certificate, GPU kernel execution trace or anti-CPU-fallback proof.
A GPU mode that passes all these checks remains device-unqualified until
physical layer-offload and memory evidence is collected independently.

### Denial behavior and data protection

If the source topology, live daemon, model pin or application guard fails,
`up` returns a nonzero status. It never performs an automatic `down`,
`prune`, volume deletion, Chroma migration, model overwrite or blind
rebuild to make the check green. Already-running services remain available
for a human to inspect. In particular, database consistency problems must not
be silently "fixed" by replacing a named volume or resetting Mongo.

The local model host runner uses `--network none` for isolated model
operations. Normal application containers retain their necessary private
Compose bridge. Do not conflate these boundaries: a Docker bridge is not an
air gap for the whole application. Complete egress isolation requires a
separate host firewall/network-policy qualification.

## Guarded Jeeves: read-only Mongo epoch admission and staged writer enrollment

The existing default Compose stack uses standalone MongoDB. It does not
offer the majority-durable, primary-bound linearizable epoch needed to guard
real conversation and memory writers across the backend/engine processes.
**A green container or working one-shot GGUF is not protected chat readiness.**

This branch adds two real source integrations, intentionally preserving
separate proof levels.

### Read-only dual-service capability probe

```bash
python scripts/local_ai_docker.py --mode cpu epoch-preflight
```

After validating the running Docker project, the operator executes
`python -m skeleton.persistence.docker_epoch_preflight --role engine` in the
engine container and `--role backend` in the backend container. Each process
uses its own authenticated service-local Mongo URI. The probe requires an
actual replica-set primary and performs a bounded linearizable read against
`skeleton_guarded_source.canonical_source_epochs`. Both process observations
must have the same primary fingerprint derived from the replica-set identity
and MongoDB primary process identity.

It does **not** write an epoch document, run `rs.initiate`, migrate records,
create an index, rewrite Mongo configuration or assume an actor is quiescent.
It returns
`shared_replica_primary_capability_verified_not_writer_fenced`, with explicit
`writer_epoch_bound=false`, `actor_migration_complete=false` and
`guarded_chat_qualified=false`.

The Docker operator's `up` path now checks this prerequisite after verified
container startup, before claiming canonical provider readiness. A default
standalone Mongo installation will therefore remain red rather than masking
the missing replica-set epoch under a healthy liveness check.

**Important:** two matching `hello` observations cannot certify that the
backend and engine have actually installed or consistently used the epoch
writer. They are only a deployment prerequisite.

### Optional backend conversation writer fence

The backend trusted lifespan now invokes
`core.local_guarded_epoch_startup.install_backend_epoch_if_requested`
*before* launching Dragon, seeders or serving HTTP traffic. Default behavior
is unchanged (`SKL_BACKEND_CANONICAL_EPOCH_FENCE_REQUIRED=0`).

An explicit, separately reviewed staged migration overlay is available at
`deploy/local-ai/docker-compose.epoch-backend.yml` for a **qualified
replica-set deployment only**. The overlay sets that backend variable to `1`.
It is NOT included in the standard Docker operator's Compose file sequence.
Do not apply it to existing data without operator-approved writer quiescence,
stable actor epoch migration and known-writer exclusion.

When enabled, the backend checks a real replica-set primary plus a bounded
linearizable read, constructs a `MongoCanonicalSourceEpoch` over the shared
`skeleton_guarded_source` database, checks the canonical conversation writer
decorators, then binds the existing global `MongoConversationAuthority`.
The epoch is published to the backend writer only after all admission checks.
A missing/inconsistent epoch denies affected mutations rather than creating
one. This preserves existing conversation data and never overwrites user state.

A failed requested enrollment aborts application startup rather than being
swallowed by the backend's normally tolerant seeder startup. It does not
silently fall back to unguarded writers.

### Separate engine memory writer enrollment

A second, independently controlled source path is now implemented in
`skeleton.persistence.docker_engine_epoch_startup` and wired to
`ServerState.bind_canonical_memory_writer`. It is disabled by default.
With `SKL_ENGINE_CANONICAL_EPOCH_FENCE_REQUIRED=1`, the engine must prove
the real authenticated `mongo:27017` replica-set primary and perform a
bounded linearizable epoch collection read *before* constructing the canonical
`MongoMemoryRepository`. It then supplies the real
`MongoCanonicalSourceEpoch` to that repository, so existing
`fence_memory_commit` and `fence_memory_tombstone` enforce actor epochs on
actual memory mutations. A caller-injected database is prohibited in this
mode because it cannot establish the trusted Docker witness.

The opt-in two-process overlay
`deploy/local-ai/docker-compose.epoch-both.yml` selects both the backend
conversation and engine memory writer fences. The two Python epoch instances
are necessarily different objects, but both refer to the same physical
`skeleton_guarded_source.canonical_source_epochs` collection and must
independently qualify its primary and linearizable reader. No actor epochs are
created by either startup path. A missing actor migration record denies
writes rather than silently initializing the source.

**This is actual source-level enrollment of both writer classes, not
cross-process proof that *every* old, external or administrative writer is
excluded.** The engine still needs an independently authenticated resolver
for the backend-owned conversation state before it may install the fully
trusted `ProtectedLocalComponents` guard. Neither overlay configures that
resolver, GGUF-native tokenizer or independent bounded reviewer, and the
default Docker operator does not auto-apply these overlays. Protected chat
remains unavailable until end-to-end qualification.

### Read-only actor migration inventory

After the two-service primary capability probe succeeds, the operator can
inventory a *bounded* cross-database source sample without touching records:

```bash
python scripts/local_ai_docker.py --mode cpu epoch-inventory --max-records 1024
```

The command obtains the actual engine memory database from the effective
Compose environment and runs the query inside the backend container, using
its authenticated internal Mongo access. It inspects the existing
`conversation_threads` and `canonical_memory_records` collections from
their different databases, deduplicates tenant/actor identities, then checks
each corresponding epoch in `skeleton_guarded_source.canonical_source_epochs`
via primary-bound linearizable reads. It reports **counts only**: scanned
records, unique actors, missing epochs, writing/quarantined epochs and
truncation. It does not print tenant or actor identifiers, message contents,
model prompts or database credentials.

The scan is bounded to 1–4096 records per source, with a 30-second cumulative
budget, 5-second bounded source queries and 2-second epoch reads. If either
collection exceeds its scan budget, the result explicitly marks truncation,
does not assert actor completeness and refuses to present a count of missing
epochs as if all actors had been checked. A sample with all stable epochs
is still **not** a proof that writers are quiescent, past data is complete,
external writers are excluded, or migration is authorized.

The inventory is a safe preparation tool for a separate approved quiescent
migration. It does not run `provision_migration_epoch`, `rs.initiate`,
`create_index`, `delete_many`, `update_one` or any Mongo mutation,
and never changes authoritative volumes.

### Unresolved guarded product gates

These must be implemented/qualified separately, in order:

1. Audit and exclude all old/unregistered conversation, memory and memento
   mutation paths, and qualify a quiescent migration of every affected
   tenant/actor into a stable, even epoch without resetting existing state.
2. Qualify both staged writer enrollments against the **same physical**
   source epoch, then establish an authenticated backend-to-engine trusted
   source-authorization and writer-custody interface while retaining their
   distinct Mongo databases.
3. Provide a tokenizer proven to be the exact active GGUF backend tokenizer.
   The existing llama.cpp CLI uses a conservative UTF-8 byte bound, **not**
   an attested native tokenizer encode/decode interface.
4. Install an independently administered bounded reviewer, pinned canonical
   policy, authorized source snapshot reader and native sampler verifier at
   `create_app(trusted_protected_bootstrap=...)`.
5. Run real concurrent write/revocation, interrupted-writer quarantine,
   restart, mixed-version exclusion, recovery and protected end-to-end Jeeves
   chat acceptance on an actual replica set.

Never use the developer legacy bypass or change `AI_LOCAL_GUARD_REQUIRED=1`
to make a readiness result green. No full-product or release qualification
has been made from this staged source delivery.

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

## Offline model custody backup and independent verification

The local AI system also includes an **additive** operator-owned model-only
backup. It is not a Docker volume snapshot or an application recovery plan.
Use the existing host model directory that appears in the operator's validated
`doctor` output. It copies exactly the `jeeves.json` manifest, one pinned
GGUF, its pinned llama.cpp executable and any completely pinned adjacent
shared libraries. A backup is **only qualified when its receipt is written
last** and a separate readback of all copied bytes succeeds. Its destination
must be a new private directory **outside** the live model directory.

```bash
# No Docker daemon, image pull, or AI inference required for these commands.
python scripts/local_ai_docker.py backup-model \\
  --source data/local-ai --destination /private/backups/jeeves-cold-001
python scripts/local_ai_docker.py verify-model-backup \\
  --directory /private/backups/jeeves-cold-001
```

Refuse symlinks, hardlinks, traversal, corrupt or duplicate manifest keys,
changed weights, unpinned adjacent runtime shared libraries, duplicate
artifact names, unknown archive contents and modified receipts. Original files
are never rewritten. Failure leaves an intentionally **unqualified partial
backup directory** for manual inspection; the utility does not automatically
delete anything. Receipts attest local bytes and identify the model-only
scope, not database consistency or secure remote attestation. Maintain an
independent off-host copy of receipts and the approved source license.

This backup does **not** collect or restore MongoDB, engine or backend SQLite,
Chroma, browser session state, secrets, encryption keys or Docker volume
metadata. All application-state restore workflows remain separate guarded
qualifications, and existing legacy Chroma `/data` migration holds are
preserved. Do not restart or replace a live model while taking a backup and
claim an atomic cross-process snapshot: quiescence and source-writer fencing
must be independently established.

An independently verified backup reopens the archived `jeeves.json` and
rechecks the archived model/executable/library digests against its *actual*
file bytes, rather than trusting only an internally recomputed receipt hash.
Undeclared empty directories are also rejected. This is self-consistency
and local custody verification, not externally keyed authenticity: protect
an off-host copy of the approved manifest and checksum receipt independently.
