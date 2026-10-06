# Runtime Supervision Contract

Machine authority: `machine/runtime_supervision.json`

VOL-004 now uses one executable lifecycle vocabulary for both the backend
application process and the Skeleton engine process. The shared authority is
`skeleton/kernel/runtime_supervision.py:RuntimeServiceLifecycle`, mirrored
byte-for-byte under the governed AI runtime tree.

The lifecycle is generation-bound and monotonic:

```text
STARTING -> READY -> DRAINING -> STOPPED
    \                         /
     \-------> FAILED <------/
STOPPED/FAILED -> STARTING only through an explicit restart generation
```

Only `READY` admits new work. Entering `DRAINING` atomically cancels the
current generation token before resource teardown begins. A restart creates a
fresh generation and a fresh cancellation token, so stale cancellation state
cannot silently poison or authorize replacement work.

The contract also derives its required external connector inventory from
`machine/ai_app_construction.json`: every provider surface with
`network_transport_owner=true` must appear exactly once and must declare a
bounded cancellation mode, timeout behavior, retry interruption semantics,
deadline propagation policy, and late-result fencing. An undeclared new network
owner fails validation.

Current cancellation classes are intentionally explicit:

- backend -> engine uses durable delegated cancellation and never invents local
  terminal truth;
- the canonical runtime-model provider uses async task cancellation plus
  request-deadline bounding;
- repository automation's blocking urllib connectors use a bounded timeout,
  pre/post-dispatch cancellation fences, and cancellable retry waits;
- late responses observed after cancellation are discarded rather than becoming
  authoritative outputs.

Validation is performed by
`scripts/check_architecture_runtime_supervision.py` and the dedicated
`VOL-004 Runtime Supervision Closure` exact-head workflow. Adversarial tests
cover illegal lifecycle transitions, generation rollover, connector inventory
drift, unbounded connectors, governed-mirror drift, pre-dispatch cancellation,
late response fencing, retry-backoff cancellation, kernel supervisor
cancellation, and the backend/engine cross-service cancellation journey.

This is implementation and qualification machinery only. VOL-004 remains
unsigned until an independent exact-head workflow succeeds and the canonical
accountability ledger can be reconciled without weakening its signing rules.
