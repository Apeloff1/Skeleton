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
The current ordinary startup does not automatically construct this new
dependency; existing callers that omit it retain their original behavior.

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
already accounts for nested cgroups/Windows commit and has its existing
short collection cache. Critical canonical serving-pressure classification
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
launch real model inference and is not native device evidence. Actual
production startup dependency injection, trusted tokenizer activation,
full-size model execution, sustained pressure, process-death/cleanup,
physical memory and device accounting, Windows/WSL2, security, release
provenance and mandatory exact-head CI remain separate requirements.
No merge or release authorization.
