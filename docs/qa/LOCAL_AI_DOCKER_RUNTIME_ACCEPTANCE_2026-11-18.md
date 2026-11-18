# Local-only Jeeves Docker — acceptance and gap closure, 2026-11-18

**Scope:** opt-in Docker deployment of the *existing* canonical Skeleton
Jeeves GGUF/llama.cpp model owner. **Branch:** `feat/docker-local-ai-runtime-20261117-r01`.
**Delivery mode:** draft PR, review-only. No merge, binary release, model
acquisition, destructive migration or product-ready claim.

This ledger separates source proof from daemon state, inference, device,
cross-process durability and release provenance. It must not be interpreted as
an assertion that a configuration-rendering test has exercised a physical host.

## 1. Architecture and trust boundaries

The application continues to use the existing Compose topology:

- `skeleton`: authoritative engine and governed local Jeeves inference.
  `AI_PROVIDER=local`, `AI_MODEL=jeeves`, protected inference required,
  no hosted or secondary credential fallback, one read-only operator-owned
  GGUF/runtime mount at `/app/local-ai`.
- `backend`: canonical application API and durable conversation writer,
  reachable at its loopback host port and linked internally to
  `http://skeleton:8001`. It cannot substitute another AI provider.
- `frontend`: browser client; build-time and runtime URLs must agree with
  the *rendered* loopback backend and engine endpoints.
- `mongo`: authenticated internal database, with canonical named
  volumes for data and configuration. **Being authenticated is not an epoch
  guarantee.**
- `chroma`: optional source-defined `full` profile only. The existing
  data migration/legacy mount hold is preserved. Merely seeing it in a
  Compose profile is not authorization to run or recreate it.

Normal services share the existing project private bridge. Docker model
pin/preflight/qualify run one-shot with `--network none`; there is no second
model API, no remote model service, and no image-embedded GGUF.

## 2. Proof levels

| Level | Evidence | What it establishes | What it cannot establish |
| --- | --- | --- | --- |
| S0 | Code review and source tests | Contract intent and adversarial denials | Actual daemon/container behavior |
| S1 | Real `docker compose config --format json` | Effective CPU/CUDA/ROCm topology admission | Containers exist, host networking works |
| D1 | `attest-runtime` on a running host | Point-in-time container IDs, image IDs, ports, live mounts, env fences, quotas and project membership | Actual GGUF inference or protected chat |
| M1 | Immutable `jeeves.json` digest preflight | Model, executable and declared library custody at the probe point | Execution succeeds or CUDA/ROCm offloads |
| M2 | Real offline GGUF one-shot receipt | Native local text generation under `--network none` with model+runtime receipt | Protected user-facing Jeeves inference |
| A1 | Canonical backend readiness endpoint | Engine-ownership/provider availability observation | Correct protected prompt handling without E2E |
| A2 | Protected end-to-end Jeeves turn | Real guarded application inference with sealed source/reviewer/tokenizer/epoch evidence | Physical GPU qualification unless measured |
| H1 | Host/driver and physical device evidence | GPU driver, binary ABI, memory/offloaded layers, observed execution | Whole product and data recovery |
| R1 | Restart-safe backup/restore rehearsal | Preservation of Mongo, SQLite, model, Chroma, session authority | Device or release provenance |
| P1 | Independent release attestation | Frozen image digest, dependency/security and signing chain, all above gates | Future host changes |

A pass at one level cannot be substituted for the next. Source CI must never
promote S0/S1 into D1, M2, A2, H1, R1 or P1.

## 3. Operational commands and stop conditions

Prepare the canonical first-install `.env` without pasting it into an issue,
log, test artifact or Pull Request. Populate a private operator-owned model
directory with an existing licensed GGUF, matching Linux llama.cpp executable
and its declared shared libraries.

```bash
python scripts/local_ai_docker.py --mode cpu doctor
python scripts/local_ai_docker.py --mode cpu build
python scripts/local_ai_docker.py --mode cpu pin \
  --model models/example.gguf --executable runtime/llama-completion \
  --profile qwen3-completion-chat --context 4096 --gpu-layers 0
python scripts/local_ai_docker.py --mode cpu preflight
python scripts/local_ai_docker.py --mode cpu qualify
python scripts/local_ai_docker.py --mode cpu up
python scripts/local_ai_docker.py --mode cpu attest-runtime
python scripts/local_ai_docker.py --mode cpu status
```

The command sequence above is illustrative, **not proof the named paths exist**.
`build` is an explicit image-build action. `up` explicitly selects
`--no-build --pull never`, so it cannot silently rebuild or pull registry
images during service activation. Both `up` and `status` now check the
live-daemon boundary. A failed `up` is deliberately nondestructive; already
running containers remain for inspection.

For NVIDIA, use `--mode nvidia` and an immutable model pin requesting a
positive GPU layer count, with a CUDA-capable matching binary. For Linux AMD,
use `--mode rocm`, declare an authorized render GID in the private `.env`
and pin a matching ROCm runtime with positive GPU layers. The operator refuses
CPU mode with positive GPU layers and GPU mode with zero requested layers.
This does not prove offload and does not authorize CPU fallback disguised as GPU.

## 4. Source/daemon protections implemented in this review branch

1. Canonical single-owner model runtime and image build profile:
   `skeleton` engine is the only inference executor.
2. Exact model/executable/library bytes: create-only immutable pin, digest
   preflight and physical one-shot inference receipt with a bounded prompt.
3. Isolated model operations: nonroot, no network, immutable root filesystem
   except the explicit create-only pin action, dropped capabilities,
   no-new-privileges and bounded memory/CPUs/PIDs/shared memory.
4. Configuration admission: exact canonical services, loopback ingress,
   browser-host API identity, authenticated internal Mongo, state volumes,
   digest-pinned databases, optional Chroma and canonical project bridge.
5. Real daemon audit: running/health status, project labels and unique service
   identity, actual port bindings, actual named volumes and bind mount
   authorities, actual environment fences, actual engine limits and device
   requests, image ID matching and whole-project running-container inventory.
6. GPU pin consistency: CPU zero layers, GPU positive layers, bounded context;
   preflight precedes any standalone inference or service launch.
7. No silent registry pull during `up`, no implicit image build, no raw Docker
   stdout/stderr reflection and no automatic data-volume removal or migration.
8. Existing CI source lanes compile, execute and qualify the Docker operator,
   full-stack Compose denial tests, live-daemon simulator denial tests, model
   backup custody tests and real Compose JSON rendering for all three modes.
9. Model-only create-only backup/verify and immutable receipt publication
   remain separate from authoritative application-state recovery.

The daemon attestation is **point-in-time** and assumes Docker's inspection
API reports host state faithfully. It does not use a cryptographically trusted
remote attestor, independent hardware probe or kernel lockdown. Observed image
IDs are necessary but not a supply-chain signature.

## 5. Non-negotiable blockers

**Protected local model bootstrap (A2):** the canonical
`create_app` path still lacks trusted `ProtectedLocalComponents`,
GGUF-backend-bound tokenizer attestation, independent bounded reviewer and
shared majority-durable Mongo source epoch across backend conversation and
engine memory writers. `local_guard_unavailable` remains an explicit deny;
lowering `AI_LOCAL_GUARD_REQUIRED` is not a repair.

**Mongo durability (R1/A2):** the default standalone Mongo container cannot
supply the required primary-bound linearizable epoch semantics. A separate
approved replica-set migration, shared epoch authority, known-writer inventory,
quiescent window, tenant/actor migration, mixed-version fencing and concurrent
writer tests are required. Do not initialize or replace the epoch during
ordinary Docker startup; do not reset existing tenant/session data.

**Physical devices (H1):** source requests for NVIDIA/ROCm and kernel-visible
device mappings are not GPU offload proof. Qualification must record host OS,
driver/runtime ABI, image and executable digests, actual observed GPU kernels,
offloaded layer count, model KV/cache and batch pressure, RAM/VRAM accounting,
mixed CPU/GPU path and multiple actual successful guarded turns. Hardware
not present in CI stays unqualified.

**Host and data protection (R1/P1):** the effective private bridge is not the
same as host-level egress prohibition. Local inference uses no network, but
application services may still have Docker networking for Mongo/backend and
other features. Operator-approved firewall/egress tests and authenticated
ingress controls remain independent. Model-only backup is not a Mongo,
Chroma, SQLite, conversation or release-asset backup. Chroma's legacy mount
requires a separate verified archive/recovery procedure before activation.

**Product completeness (P1):** Windows 11/WSL2, native CPU, CUDA and ROCm
tests, recovery, first-install UI/API, security workflows, exact-head native
binary custody and release provenance all require new head-specific evidence.
No source-level result can waive a failed or pending mandatory gate.

## 6. CI discipline

Run against the **current commit SHA**, never an ancestor:

```bash
python -m compileall -q \
  scripts/local_ai_docker.py \
  scripts/local_ai_compose_boundary.py \
  scripts/local_ai_runtime_attestation.py \
  skeleton/app/docker_local_ai.py
python -m pytest -q --noconftest --maxfail=8 \
  skeleton/testing/test_docker_local_ai.py \
  skeleton/testing/test_local_ai_compose_boundary.py \
  skeleton/testing/test_local_ai_runtime_attestation.py \
  skeleton/testing/test_local_ai_model_backup.py \
  skeleton/testing/test_qualify_local_ai_compose.py
python scripts/qualify_local_ai_compose.py
```

Physical tests are intentionally omitted from the CI-only command. Tests must
verify positive local layouts **and denial** of wrong ports, bridged networks,
unqualified sidecars/Chroma, absent or duplicated volumes, stale image IDs,
credential mismatch, privilege expansion, resource drift, GPU request drift,
contradictory model pins and malformed private Docker responses.

## 7. Canonical source epoch staging — guarded Jeeves repair wave

The Docker deployment now contains a distinct **read-only Mongo capability**
phase and independently opt-in canonical writer enrollment components:

- `skeleton/persistence/docker_epoch_preflight.py`: primary-bound
  `hello` and real linearizable epoch collection read, run in both
  engine and backend containers. A hashed primary identity must match.
  A standalone Mongo server fails rather than being called epoch-capable.
- `backend/core/local_guarded_epoch_startup.py`: backend trusted lifespan
  binds the real global `MongoConversationAuthority` to a
  `MongoCanonicalSourceEpoch` only when explicitly requested and after
  exact decorated-writer inventory and live primary/read qualification.
  This precedes other background work; requested failure aborts startup.
- `skeleton/persistence/docker_engine_epoch_startup.py`: engine memory
  writer enrollment, enforced inside `ServerState.bind_canonical_memory_writer`,
  with real primary and linearizable-read admission. Explicitly requested
  fencing cannot be bypassed by optional memory initialization shortcuts or
  caller-injected database handles.
- `deploy/local-ai/docker-compose.epoch-backend.yml` and
  `deploy/local-ai/docker-compose.epoch-both.yml`: manually selected,
  review-only migration overlays. The default Docker operator does not apply
  them or automatically migrate existing Mongo data.
- `skeleton/persistence/docker_epoch_inventory.py`: bounded read-only
  inventory of canonical `conversation_threads` in the backend database
  and `canonical_memory_records` in the engine database. Epochs are
  checked in the fixed shared `skeleton_guarded_source` database.
  Reports counts and incomplete/quarantined states without actor identifiers.
  A clean sample is never promoted to quiescence or external writer exclusion.
- Existing Backend Quality and first-install CI lanes now compile and
  exercise these source paths, including denial behavior and simulated
  primary, writer, actor, migration and privacy regressions.

**Critical separation:** independent Python epoch objects can share one
physical Mongo epoch collection while the two services retain different
application database namespaces. They cannot, by themselves, prove that
all historical and externally deployed writers obey that fence. The
application still lacks an authenticated engine-to-backend conversation
resolver, production GGUF-bound native tokenizer, independently administered
reviewer, stable actor migration acceptance and real guarded end-to-end
Jeeves qualification. None of the source changes provisions epoch records,
changes a Mongo replica set, drops collections, or enables hosted fallback.

Command examples (review-only, read-only):

```bash
python scripts/local_ai_docker.py --mode cpu epoch-preflight
python scripts/local_ai_docker.py --mode cpu epoch-inventory --max-records 1024
```

Both require real running containers, authenticated Mongo and the
pre-existing storage authority. Standalone Mongo will reject the
capability stage. They do not repair the database automatically.

## 8. Review, recovery and rollback policy

Keep the PR draft until every required gate and actual host evidence is
satisfied. Do not squash or merge merely because a subset of source checks
passes. For a failed Docker boundary, use read-only diagnosis before changing
images or volumes. For a stale image, inspect the existing container
configuration and independently preserve data before any deliberate replacement.
Never treat `docker compose down --volumes` as recovery. For model migration,
create a fresh immutable pin and preserve verified old bytes; do not edit an
existing receipt or model blob in place. Restore application state only through
independent qualified Mongo/SQLite/Chroma procedures, not the model-only
backup utility.


## 9. Explicit offline model-artifact restore into a new private directory

The original `backup-model` utility remains backup-only. The opt-in
`restore-model-backup` and `verify-model-restore` subcommands perform
**physical pinned-byte copy/rehash** with no model inference, Docker daemon,
Mongo migration, or automatic app configuration.

```bash
# The source backup must already be verified; choose a NEW, nonexistent
# destination outside the current model mount and backup directory.
python scripts/local_ai_docker.py verify-model-backup --directory ./private-model-backup
python scripts/local_ai_docker.py restore-model-backup \
  --source ./private-model-backup --destination ./new-restored-model
python scripts/local_ai_docker.py verify-model-restore --directory ./new-restored-model
```

Restore admission verifies every source backup pin and digest **before**
creating a new target. The target must have a genuine, nonsymlink parent
and must not exist. Files are copied with exclusive-create and
no-follow flags; the runtime executable receives owner-only execute
permission on its pinned inode. A new restore receipt is written **last**
and includes the complete verified model/runtime inventory, original
backup receipt digest, and `application_state_restored=false`,
`inference_executed=false`, `device_qualified=false`, and
`chat_guard_qualified=false`. Unknown files, unreadable or corrupt
receipts, symlinks, mismatched pinned model bytes and hard links are denied.

A failed restore preserves the partial target directory without a
completed receipt so an operator can investigate it; it never cleans,
overwrites or activates the live model. A separately validated
deployment-manifest/path switch, authenticated database backup/recovery,
container image and startup, physical native inference, GGUF tokenizer,
independent reviewer, source epoch migration and release attestations
remain **outside** this functionality.

CI runs synthetic tiny model artifacts and verifies copy/tamper/denial
behavior only. No CI source test qualifies an actual installed model,
an application restore or a physical Docker host.
