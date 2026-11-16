# Offline runtime execution custody

Companion to UNIFIED_OFFLINE_RUNTIME_ADMISSION.md. This source integration
retains the historical sealed-page, request admission, token iteration
and local inference owners. It exposes three distinct mechanisms, all
for a trusted local application process.

## Sealed source custody

`sealed_cpu_custody` accepts an independently pinned WeightLoadPlan
digest, full canonical ModelIdentity, explicit CPU policy and a bounded
sealed-copy ceiling. Inventory and optional GGUF framing are verified
before copying. The pre-copy check reserves both the sealed copy and
projected weight placement. The original Linux memfd owner hashes the
copied bytes, applies write/grow/shrink/seal locks and maps read-only.
A second measured preflight is required before yielding the mappings.

The mappings live strictly within the context. Consumers must release
all exported views before context exit. No GPU, Windows, unsealed or
hosted fallback exists. Sealed bytes are not decoded tensors, committed
physical RAM, or a backend weight-binding attestation.

## Incremental request owner

```python
from skeleton.app.offline_runtime_preflight import RuntimePolicy
from skeleton.app.offline_runtime_queue import QueuePolicy, reserve_cache, OfflineRequestQueue
from skeleton.app.offline_runtime_session import OfflineRuntimeSession
from skeleton.ai.model_runtime.flgb_model_runtime import BatchRequest

base = RuntimePolicy(backend="cpu")
queue_policy = QueuePolicy()
session = OfflineRuntimeSession(
    store_path, plan_digest=plan_digest, model_identity_digest=model_digest,
    policy=reserve_cache(base, queue_policy),
)
queue = OfflineRequestQueue(session, queue_policy, trusted_slice_executor, base_policy=base)
try:
    queue.submit(BatchRequest("request-1", 128, 32), timeout_ms=30000)
    # Call tick only from a trusted owner loop.
    observation = queue.tick()
finally:
    queue.close()
```

The existing RuntimeAdmissionScheduler owns bounded pending/active
requests and logical KV reservations. The full KV ceiling is added to
the base host reserve, independent of weight and worker accounting.
No request may exceed the per-request token ceiling, queue capacity
or the per-token KV estimate budget. This is CPU-only; actual KV
allocation size and placement remain with the execution owner.

Every iteration is serialized and uses a fresh local hardware
observation, canonical iteration scheduling and exactly one consumed
grant. Prefill cannot report decoded completion; decode cannot start
before the prompt is fully processed. Partial progress is retained; a
trusted synchronous executor reports only the granted phase/count.
Cancellation and deadlines are checked before and after each slice.
Cache capacity is released only after the executor's release callback
succeeds. No retained KV is advertised. An erroneous executor poisons
the supervisor, signals cancellation and closes further admission.
Its suspect allocations remain accounted until explicit cleanup.

The executor is an internal trusted protocol, not a plug-in import,
remote procedure or external command. It must implement real allocation,
prefill, decode, release and cooperative cancellation. A blocked kernel
cannot be forcefully interrupted by this Python supervisor. Shutdown
signals cancellation without waiting indefinitely; a running tick may
still own resources until it returns.

## Whole-request execution

The existing LocalInferenceEngine is not assumed to implement incremental
kernels. MeasuredWholeRequestEngine uses its real asynchronous generate
method only when the complete bounded input plus output reservation fits
one fresh grant. It preserves the existing engine's guarded-context,
tokenizer, resource, cache and deadline checks. Partial grants are
deferred without dispatch. The externally retained backend digest is
checked before and after execution. Late/cancelled results are not
published by this adapter. No tool execution authority is granted.

The adapter returns an in-process result plus a compact digest receipt.
It does not print prompts or results. The host still owns the engine and
its shutdown lifecycle. The separately approved model-store identity and
backend digest are distinct; the adapter cannot prove a backend consumed
these sealed mappings. It does not change the production Jeeves default
inference route or bypass guarded context.

## Qualification

```sh
python -m pytest -q skeleton/testing/test_offline_execution_custody.py skeleton/testing/test_offline_runtime_admission.py skeleton/testing/test_offline_weight_inventory.py skeleton/testing/test_pressure_iteration_scheduler.py
python -m compileall -q skeleton/app/offline_runtime_custody.py skeleton/app/offline_runtime_queue.py skeleton/app/offline_runtime_whole_request.py skeleton/app/offline_runtime_session.py
```

Also run the existing canonical admission, sealed page, local inference,
CPU/energy/pressure, GGUF and installer suites. Regression code contains
explicitly mocked hardware, a cooperative executor test double and a
real reference inference engine case. These are not claims of measured
physical inference, native tensor qualification or a passing test run.
Full-size model and KV allocation, actual kernel cancellation, native
multidevice execution, loader-to-sealed-byte binding, guarded Jeeves
wiring, process recovery and independent security/device/release evidence
remain outstanding. No merge or release authorization.
