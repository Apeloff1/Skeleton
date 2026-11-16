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


## Source-store and lifecycle corrections

The canonical store now limits each manifest to 16 MiB and checks a
regular-file descriptor's observed identity before and after reading.
The inventory admits all declared plan sizes before opening any weight
object, retains fixed-size declarations, and checks the final manifest
name set. This bounds the object hashing work by the admitted declared
aggregate (plus per-object boundary detection), not the number of
discovered models multiplied by the entire store budget.

Decoder streams are now the same descriptors hashed and rewound by the
store. Plan and weight identity come from a single bounded manifest read.
This removes the verify-path/close/reopen gap. It does not prevent an
authorized writer from modifying an already opened ordinary file during
use; the Linux sealed-page owner remains the immutable-copy authority.
Parent-path and platform-specific security also require their separate
qualification.

The cooperative iteration controller now rejects nonadvancing offer
clocks, noncanonical phase values and public policy/source replacement.
Malformed consumption invalidates the outstanding grant. Queue shutdown
reports whether an iteration still owns reservations. Closing while a
slice is running signals cancellation; the iteration owner drains on
return. An executor failure retains suspect reservations until explicit
cleanup succeeds. Logical drain is not an OS-level process-death receipt.

Focused regression sources cover aggregate rejection before reads,
oversized sparse manifests, symlink rejection, inventory drift, descriptor
replacement and concurrent queue closure. These cases have not yet been
executed against the final branch head.


## Scoped admission and mid-copy fences

The local hardware collector now intersects the standalone host memory
probe with the canonical serving owner's process-scoped allocation
headroom (including nested Linux cgroup and Windows commit constraints).
An unavailable scoped memory counter does not become unrestricted memory.
Each real observation includes the canonical pressure classification and
digest; critical pressure blocks ordinary offline placement and iteration,
not just the guarded native startup route. Fixture-only pure planning still
accepts explicitly constructed observations and is not physical evidence.

The sealed-page owner accepts an optional trusted progress checkpoint.
It checks before copying, before exceeding each 64 MiB interval, and at
the exact completed byte total before publishing any mapping. The
offline custody wrapper uses this checkpoint to remeasure pressure and
reserve the remaining copy separately from downstream placement and
worker headroom. Rejection closes all unpublished resources. These are
allocation admission checks, not an OS reservation or interrupt for a
blocked filesystem write.

If a caller leaves an exported memoryview alive, the corresponding mmap
cannot be forcibly closed. Cleanup nevertheless attempts every other
mapping and original memfd descriptor; it raises an explicit incomplete
cleanup error instead of claiming successful release.

The existing sealed-context workflow includes the offline admission,
execution custody, inventory, measured deployment and native lease
regressions in its additive guarded regression step. No existing required
checks or merge holds are relaxed. The offline console entrypoint is present
in both supported root metadata sources. The governed server mirror has
been synchronized without replacing the two credential-bearing provider
facades. Full CI, physical cgroup/commit/thermal qualification and actual
native model execution are not established by these source changes.


## Exclusive cooperative execution and source freshness

A session handed to a cooperative request queue or whole-request adapter
now has exactly one claimed in-process execution owner. Claiming revokes
prior pending grants and recovery state. Unrelated consumers cannot
offer, consume or revalidate through that session. This identity-based
fence is a trusted-code integration contract, not a security sandbox
against arbitrary Python running in the same interpreter. Independent
sessions and direct backend callers still require their own coordinated
resource budgets.

The queue permits explicit reinspection only while no pending or active
request and no iteration remain. The whole-request adapter serializes
reinspection with execution. Its reinspection timeout bounds lock
waiting, not disk hashing. A session may be constructed with an explicit
`maximum_source_age_ns` between one nanosecond and one day. When set,
source inspection expiration revokes pending admission and refuses
further offers/consumption until explicit reinspection. This is a
completion-timestamp freshness bound, not continuous file integrity or
immutable source residency. Without this opt-in limit, prior behavior
remains explicit reinspection. An expiration or failure during active
queue execution may poison the queue; finish cleanup and reopen a newly
inspected session rather than silently regranting work.

Whole-request lock waiting now consumes the original caller timeout and
is bounded without cancelling the current owner. Admission and result
publication still use the earlier of the caller deadline and the
consumed grant expiry. Output receipt digests bind hashes of the UTF-8
text and canonical structured result separately from bounded metadata;
a large valid multibyte result no longer expands the compact diagnostic
receipt past its serialization ceiling. The receipt does not retain
result text or grant further authority.

The source regressions include exclusive ownership, competing adapters,
deadline-bound wait, compact Unicode custody digests, expiry before
consumption and idle-only reinspection. Tests remain subject to
exact-head CI, independent runtime qualification and all existing holds.


## Bounded nonproductive work and expiry

The cooperative queue has an explicit `max_stalled_slices` policy
(default 8, bounded from 1 through 1024). Only dispatched slices
returning zero tokens without a terminal result count toward this
limit; scheduling deferral and pressure-induced no-grant iterations
do not. Actual token progress resets the consecutive counter. When the
limit is reached, cancellation and executor release precede return of
the logical KV slot and the request is retired as stalled, not as a
successful result. Successfully confirmed executor releases are not
repeated if subsequent scheduler bookkeeping fails. A release that
raises is still unconfirmed and needs the existing explicit cleanup
path. This cannot interrupt a permanently blocked executor.

Both cooperative and whole-request paths intersect the consumed grant's
exclusive expiry with the operator-configured source inspection
expiry, if present, and with the request's deadline. A result returned
at or after that deadline is not successful publication. An observation
that raises during admission now clears pending proposals and warmed
energy recovery state. No receipt can be consumed at its exact expiry.

Added focused regression sources for malformed offer recovery, exact
expiry, stalled resident slot release and source-bound deadline
calculation. No new physical executor capability or qualification is
claimed.
