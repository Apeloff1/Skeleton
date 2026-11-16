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


## Noncreating model-store inspection and heterogeneous packing

Read-only weight store opening now requires an existing root, objects
directory and manifests directory. It does not invoke directory creation
or permit staging. The inventory, selected-source preflight and sealed
loader use this mode. A store instance binds the observed identities of
its managed directories; it rejects changed layouts, symlink/reparse
directories and observed object-bucket replacement during verified
reading. Manifest declarations require an exact integer schema version,
bounded list of shards and canonical shard fields. External ancestors
remain the responsibility of the trusted store operator. These
portable identity comparisons do not provide an adversarially immutable
directory-descriptor traversal, filesystem isolation, or Windows ACL
qualification.

The canonical placement owner retains successful historical
largest-free placement when no preference is supplied. Failure now
tries bounded deterministic descending-size largest-free and best-fit
packings, preserving the original shard indices in the final output.
An optional device-kind preference may guide these attempts;
neutral fallback is permitted by the generic packing owner, but
hybrid preflight requires that at least one actual shard be placed on
the CUDA device. Hybrid host capacity preserves a minimum worker
allowance before model placement, and canonical worker/energy checks
continue to tighten execution admission afterward. No single shard may
consume combined capacity split across devices.

The packing alternatives address order-dependent fragmentation, not
arbitrary global bin-packing optimality. A rejected bounded packing is
not a proof of impossibility. Placement receipts still do not perform
native tensor allocation, migration, offload or physical GPU execution.
Focused regressions are added for directory replacement, read-only
inspection, malformed manifests, packable fragmentation cases and
hybrid accelerator selection. Exact-head test execution is outstanding.


## Per-device pressure and exact inventory manifest evidence

NVML captures each enumerated adapter's bounded total, free and used
counters, including exhausted adapters excluded from placement. The
receipt checks agreement between those observations, aggregate counters
and available placement descriptors. Its ordinal identifiers are scoped
to the probe, not persistent physical identifiers or verified CUDA
runtime device mappings. No MIG, visibility, allocation or execution
qualification is implied.

For CUDA and hybrid candidates, projected occupancy is now the largest
projected fraction among the GPUs actually assigned weight shards.
Unrelated idle GPUs cannot hide congestion on a selected GPU; unrelated
full GPUs are not themselves a reason to throttle a different selected
adapter. Per-device free bytes must still preserve the separately
configured reserve. Legacy aggregate-only fixtures can exercise pure
planning, but aggregate-only live observations cannot authorize GPU work.
Host and GPU pressure continue to be evaluated independently. The
calculation does not measure runtime scratch, actual resident tensors or
physical device allocation.

Inventory also commits the SHA-256 and bounded byte length of every
complete canonical manifest. These cover fields outside the load-plan
digest, including the independently represented weights identity. The
metadata digest records observed identity; it is not an authentication
signature. An operator must independently pin trusted source identities.

Before weight-object verification the inventory now admits separate
aggregate metadata and shard-reference ceilings (defaults 64 MiB and
262,144 references). The standalone inventory CLI exposes
`--max-manifest-bytes` and `--max-shard-references` for explicit bounded
operator configuration. Read-only verification uses each admitted
manifest's exact SHA-256 and byte ceiling. A final pass compares all
manifest identities, including earlier manifests while later models were
being verified. Selected-source preflight also binds the exact manifest
observed by the inventory, rechecking after the selected GGUF inspection.
This is bounded observed consistency, not an atomic filesystem snapshot
or a lock against hostile concurrent store writers.

Regression sources cover exhausted device visibility, inconsistent
per-device counters, maximum selected-device pressure, live aggregate-only
denial, metadata/reference budget admission and same-plan manifest field
changes. Existing inventory receipts change because the covered evidence
has expanded; persisted prior inspection digests must be explicitly
revalidated rather than silently accepted. Physical GPU execution,
native device mapping and exact-head test results remain outstanding.


## Sequential sealed loading and staged byte admission

Selected-source receipts now carry the independently observed complete
manifest SHA-256 and byte count. The sealed loader binds that manifest
to both model identity fields, checks its byte and mapping bounds,
then verifies each shard while copying directly from its owned source
descriptor into a private memfd. It no longer opens every source
descriptor simultaneously or conducts a separate full prehash inside
the sealed-copy owner. The earlier inventory/source inspection still
performs its own verification. Each original memfd descriptor is closed
after mapping and sealing; Python's mapping can retain its own
descriptor. All mappings remain private until the whole copy and final
manifest check succeed. Ordinary verified decoder streams also check
manifest identity before publication and after synchronous use.

The default sealed mapping ceiling is 256, configurable up to 4096
by the trusted caller. This is a logical bound, not a promise that an OS
descriptor limit, physical memory quota or mapping limit will permit it.
Progress checkpoints and thermal/resource checks remain in force.
No unsealed fallback is provided.

Staging now validates manifest serialization, existing manifest
consistency, source indices and duplicate digest size declarations
before ingesting new objects. The optional `maximum_new_bytes` argument
counts distinct absent content-addressed objects, not repeated logical
shard references. Existing objects are verified; a zero new-byte
allowance permits an already-present model without approving missing
objects. This per-operation preflight is not a shared disk quota or
a durable concurrent-writer reservation. Valid CAS objects from a
partially failed later ingestion can remain unreferenced; manifests
are published only after the full plan verifies. No automatic deletion
or garbage collection is introduced.

Focused regressions cover mapping ceilings, sequential source ownership,
manifest drift at copy completion, distinct absent-byte limits and
pre-ingest manifest bounds. Actual platform qualification and all
required exact-head checks remain outstanding.


## Cooperative weight-store disk admission

The optional `WeightStoreDiskOwner` composes the canonical store's
existing staging path with a private POSIX writer lock, bounded
inventory and explicit free-space reserve. Participating writers use
the same preserved lock inode and the same trusted operator policy.
The scan accounts for all canonical object and manifest file lengths,
including unreferenced objects, and refuses unexpected temporary files,
links, noncanonical bucket names and mixed filesystems. Prospective
object, bucket, manifest and byte ceilings are evaluated before staging.
Actual temporary object and manifest writes are independently charged
and recheck the observed filesystem free-space reserve. The final
inventory must reconcile with the bytes actually charged.

```python
from skeleton.ai.model_runtime.weight_shard_store import WeightShardStore
from skeleton.ai.model_runtime.weight_store_disk_owner import (
    DiskAdmissionPolicy, WeightStoreDiskOwner,
)

store = WeightShardStore("/private/service/weights")
owner = WeightStoreDiskOwner(store, DiskAdmissionPolicy(
    maximum_store_bytes=256 * 1024**3,
    minimum_free_bytes=8 * 1024**3,
))
# Trusted local caller supplies the canonical identity, plan and paths.
# key, receipt = owner.stage(identity, plan, source_paths)
# observed = owner.inspect()
```

This is opt-in cooperating-writer admission, not a hard physical disk
quota or filesystem isolation. Direct legacy staging bypasses the
shared lock; all participating processes must use the owner. The private
root, policy and lock inode must remain stable under trusted operator
custody. File lengths do not include filesystem allocation rounding,
metadata, snapshots or unrelated processes' writes. A disk failure or
unexpected file may require recovery review; no automatic deletion,
rollback of already published immutable objects, or filesystem-wide
reservation is claimed. The ordinary staging path also enforces its
per-operation new-object cap at the actual write boundary rather than
only the initial existence check.

Regression sources cover cooperating contention, orphan accounting,
free-space and prospective entry limits, interrupted temporary files,
lock replacement and stale existence observations. They are selected by
the existing sealed-context workflow. Native Windows locking, platform
qualification, crash injection on real storage and final-head CI remain
outstanding.
