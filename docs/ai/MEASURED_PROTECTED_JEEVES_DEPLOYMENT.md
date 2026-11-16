# Measured protected Jeeves deployment

The historical offline resource owners now have an opt-in connection to
the existing ProviderRegistry local activation path. The deprecated
`skeleton.jeeves.local_inference_bridge` remains fail-closed. No old
bridge dispatch, hosted fallback, new provider or unguarded route is used.

## Trusted startup contract

Use the existing environment policy (JEEVES_LOCAL_ONLY=1, AI_PROVIDER=local,
AI_LOCAL_GUARD_REQUIRED=1, and exactly one AI_LOCAL_DEPLOYMENT_PATH).
The application startup must independently retain the canonical manifest
digest, raw manifest SHA-256, artifact byte ceiling and approved weight-store
plan/model identity. It constructs the following typed dependency:

```python
from pathlib import Path
from skeleton.app.offline_runtime_preflight import RuntimePolicy
from skeleton.app.offline_runtime_llama_binding import MeasuredLocalDeployment
from skeleton.provider_runtime import ProviderRegistry

measured = MeasuredLocalDeployment(
    manifest_digest=approved_canonical_manifest_digest,
    manifest_sha256=approved_raw_manifest_sha256,
    maximum_deployment_bytes=approved_deployment_byte_ceiling,
    store_path=Path("/private/weights"),
    plan_digest=approved_plan_digest,
    model_identity_digest=approved_model_identity_digest,
    policy=RuntimePolicy(backend="cpu"),
)
registry = ProviderRegistry.from_env(
    guarded_components=application_owned_native_tokenizer_and_context_components,
    measured_local_deployment=measured,
)
```

Do not derive the expected pins from an untrusted candidate at activation.
The existing ProtectedLocalComponents must supply real independently trusted
snapshot, reviewer, active tokenizer, sampler and projection authorities.
This integration does not invent them or enable a mock attestor in production.
The default startup does not fabricate this dependency; existing callers
that omit it retain their original behavior. The actual ASGI composition
root now accepts it explicitly.

Measured mode rejects hosted selection, legacy reference artifacts, catalogs,
unguarded activation, configured caches, and concurrency greater than one.
It retains the original governed provider wrapper and Jeeves model-id policy.
Failures are unavailable status, not authorization to try an unmeasured or
hosted route. The original default seed and queue/batch configuration are
preserved. Only the explicit protected CPU GGUF deployment is supported.

## Source and runtime fences

LocalModelDeployment.load checks the raw manifest digest before expensive
artifact admission and enforces its deployment byte limit. Its separate
canonical manifest digest must also match. The existing artifact owner binds
the native executable, GGUF, configured libraries and model identity. A
single independently verified store shard must match the GGUF's exact digest
and size. The new gate requires the native owner's actual GGUF framing check,
explicit threads/context, zero GPU layers, the canonical host/backend KV
setting, and automatic artifact rehashing each execution.

Only the existing fixed completion profiles or no extra arguments are
allowed, and caller-supplied environment overrides are not admitted.
The gate pins the execution profile. The native owner continues to enforce
its already existing artifact checks and actual guarded context admission.
Digest agreement does not prove immutable opened-file custody in the
external process or that the executable implemented the intended tensor
operations.

## Resource accounting and launch rejection

The new gate reserves context-wide KV from the larger of the available
operator and canonical model geometry estimates. No missing estimate is
accepted. It also accounts for native scratch, weight placement, operator
reserves and per-worker costs. The original power policy can reduce the
admitted worker ceiling; the pinned native thread count must fit that ceiling.
The gate does not change native flags or operating-system clocks.

The native owner invokes the callback both before prompt processing and
again immediately before attempting to spawn the native child. Each callback
obtains a local power/topology sample and intersects its available memory
with the existing serving probe's scoped allocation headroom. The latter
already accounts for nested cgroups/Windows commit. Both native launch
checks request an uncached collection; ordinary serving maintenance retains
its existing short collection cache. Critical canonical serving-pressure classification
also denies the launch. Unavailable headroom denies activation for that
request rather than counting host memory with unknown scoped availability.

This is conservative CPU admission for a single canonical engine. It is not
an OS reservation, an aggregate cross-process budget, physical RAM/KV
qualification or guarantee against pressure changes after process launch.
The existing native cancellation, child custody and provider accounting
owners remain responsible for running work.

## Status and shutdown

`registry.measured_local_status()` returns None for ordinary activation or a
bounded redacted gate status for the selected mode. It does not obtain a new
hardware reading. The governed adapter status also exposes the last measured
check, with exact source/runtime/profile and preflight digests, reserve sizes,
pressure classification and blockers. A candidate is not a qualified model.
Closing the governed adapter first closes the measured gate, then invokes
its existing engine shutdown. The gate does not start or kill processes.

## Qualification

```sh
python -m pytest -q skeleton/testing/test_measured_jeeves_deployment.py skeleton/testing/test_offline_execution_custody.py skeleton/testing/test_offline_runtime_admission.py
python -m compileall -q skeleton/app/offline_runtime_llama_binding.py skeleton/provider_runtime.py
```

Also run existing protected context, provider registry, native launcher,
deployment, sealed-page and physical inference quality suites. The new
regression uses a tiny framing-only artifact, a test-only tokenizer attestor,
mocked resource probes and the actual native launch hooks. It does not
launch real model inference and is not native device evidence. Actual deployer-owned production configuration, trusted tokenizer activation,
full-size model execution, sustained pressure, process-death/cleanup,
physical memory and device accounting, Windows/WSL2, security, release
provenance and mandatory exact-head CI remain separate requirements.
No merge or release authorization.


## ASGI and engine startup

The public application factory and the existing server runner accept an
explicit trusted `measured_local_deployment` dependency:

```python
from skeleton.api.server import create_app

app = create_app(
    trusted_protected_bootstrap=install_real_protected_authorities,
    measured_local_deployment=measured,
)
```

The trusted bootstrap must install the canonical native guard and the real
Mongo conversation and memory owners using their shared majority-backed
writer epoch. The application may alternatively install the typed measured
dependency once through
`state.configure_engine_measured_deployment(measured)` inside that bootstrap.
Do not supply it both ways. Neither HTTP nor an environment variable can
construct this dependency or substitute a verifier. The engine's direct
binding entrypoint validates these authorities before opening durable
execution stores. The frozen dependency is forwarded when the exclusive
execution coordinator activates its provider registry, with no alternate
provider or independent chat route.

An ordinary Docker factory invocation without a trusted bootstrap is not
an activated measured deployment. It remains possible to boot application
services with the AI provider unavailable. Real product commissioning must
supply the independently administered authorities and pins; these example
identifiers are not provided operator values. A selected measured activation
cannot fall back to an unmeasured route on a pin or authority error.

## Operator inspection before startup

The installed offline runtime command now has a read-only deployment check:

```sh
python -m skeleton offline-runtime deployment-check \
    --store /private/weights \
    --plan-sha APPROVED_PLAN_SHA \
    --model-identity-sha APPROVED_MODEL_SHA \
    --deployment /private/deployment.json \
    --manifest-sha256 APPROVED_RAW_SHA \
    --manifest-digest APPROVED_CANONICAL_DIGEST \
    --deployment-budget-mib 16384 \
    --require-candidate
```

Choose the deployment budget to cover the independently approved manifest,
model, executable and adjacent libraries, not just GGUF size. This command
requires all four deployment-specific inputs and CPU GGUF framing. It
reuses the actual deployment/source resolver and native profile validator,
reads the artifacts, and performs one scoped local resource check without
creating a provider, supplying a tokenizer attestor or starting inference.
A first report of candidate status is not permission to dispatch. There is
no transferable grant; protected authorities and native/release evidence
remain unassessed. Exit 2 denotes invalid input/evidence/profile; exit 3
with `--require-candidate` denotes a recorded blocked observation.

If a later native evidence collector fails, the gate now replaces any
previous candidate observation with a bounded denial receipt. A cached
successful status cannot represent the last check after rejection. These
records are diagnostic observations and do not attest execution results.

The added server and CLI regressions exercise typed startup fences, actual
registry activation, and fresh pressure collection. They are not production
Mongo, native tokenizer, OS allocation or physical hardware qualification.


## Optional shared native process lease

The trusted measured deployment configuration may additionally supply
`lease_directory=Path("/private/shared-native-slot")`. Provision that
directory in advance, owned by the service principal with mode 0700.
Every cooperating process on the host must use the same stable directory
and lock inode. Do not delete, rotate, rename, or recreate its empty
`native-cpu.lock` while any owner or child may remain alive. This option
currently requires POSIX flock and descriptor-relative opens. A deployment
without it retains the previous single-engine resource checks and does not
claim cross-process exclusion. No automatic Windows fallback is provided.

The native resource lease factory acquires an exclusive nonblocking lock,
checks the private file and directory identities, then repeats measured
resource admission while holding the slot. The llama.cpp launcher combines
the resulting nonsecret descriptor with any existing outer HTTP lease
rather than replacing that authority. Closing the parent reference never
issues LOCK_UN on the shared open file description. A native child that
retains the inherited descriptor can keep the kernel lock across parent
death; arbitrary executables that close inherited descriptors are not
qualified by this mechanism. It is cooperative process exclusion, not a
physical memory reservation or host-wide quota. An operator-controlled
private directory and stable lock inode remain a trust prerequisite.

The canonical inherited-lease context also binds observed descriptor
identity and revokes copied contexts when the owner leaves its scope.
Numeric descriptor reuse for a different inode is rejected. The checks
do not independently authenticate the advisory-lock acquisition or prove
open-file-description identity when an inode is reopened.

A failed native termination no longer automatically clears active process
accounting or releases the native lease. The launcher keeps the process,
pump and callback references for unconfirmed cleanup. Explicit
`reap_unconfirmed_cleanup()` retires only children for which the retained
handle confirms exit and all recorded pumps have stopped; release must
succeed. It never signals a PID recovered from a receipt. The local engine
calls it during shutdown, refusing physical-drain completion while native
cleanup remains unconfirmed. The coordinator's existing retryable shutdown
can retain its durable database ownership during that interval.

```sh
python -m pytest -q skeleton/testing/test_native_process_lease.py skeleton/testing/test_measured_jeeves_deployment.py
```

The new regressions include a real trivial child-process inheritance case,
not a real llama.cpp model launch. Actual abrupt-supervisor-death testing
with the approved runtime, native descriptor retention, complete child
process-tree containment, sustained resource pressure, cross-process
deployment qualification and Windows Job Object semantics remain independent
holds. No merge or release authorization.
