# Runtime Supervision Contract

Machine authority: `machine/runtime_supervision.json`

## Purpose

VOL-004 defines one runtime-supervision model for the application backend,
engine API, durable engine executions, and every declared network-transport
owner in the AI construction contract.

The v2 contract is intentionally stronger than process liveness. A service is
not considered operational merely because a socket is listening. Work
admission, cancellation, drain, restart, provider I/O, and completion authority
must all agree on one generation of runtime state.

## Lifecycle authority

The canonical implementation is
`skeleton/kernel/runtime_supervision.py`; the governed AI-tree mirror is
`skeleton/ai/runtime/kernel/runtime_supervision.py`. The two files are required
to remain byte-identical.

Each service has exactly one active generation with these phases:

`STARTING -> READY -> DRAINING -> STOPPED`

or

`STARTING/READY/DRAINING -> FAILED`.

Only READY accepts new external work. Durable engine recovery is the sole
explicit STARTING admission exception. DRAINING atomically cancels the
generation token and revokes new-work authority before dependency teardown
begins.

STOPPED is not a cosmetic state: it cannot be asserted while generation-bound
work leases remain.

## Generation-bound work leases

HTTP requests and engine executions are represented by immutable work leases.

A lease binds:
- service identity;
- work identity;
- lifecycle generation;
- monotonic lease sequence;
- monotonic acquisition time.

Duplicate live work IDs are rejected. Restart is impossible while leases remain.
A restart creates a fresh cancellation token and generation number, so stale
leases and stale cancellation authority cannot be reused after recovery.

The engine coordinator binds leases to exact asyncio task identity, not merely
execution ID. This specifically fences a delayed done-callback from an old task
from releasing a newer task's lease after the same durable execution identity is
re-driven.

Generated request leases are minted by the lifecycle authority itself. Their
identity is `<prefix>:<generation>:<monotonic_lease_sequence>`; Python object
identity is explicitly forbidden. This prevents process-local object-ID reuse
from becoming part of admission authority or operational evidence.

Backend startup work is governed by the same lease set. Both asyncio boot tasks
and raw daemon threads acquire generation-bound leases before they start and
release them in `finally`. Thread delay waits use the lifecycle cancellation
event rather than blind sleeps, and shutdown joins tracked threads before
closing Mongo. If an asyncio task, thread, or lease remains after the bounded
drain window, shutdown fails closed and the service remains DRAINING instead of
claiming STOPPED.

## HTTP admission

Both backend and engine install the same framework-neutral
`RuntimeAdmissionMiddleware`.

The middleware:
- admits only when the lifecycle grants work authority;
- acquires a work lease before invoking the handler;
- releases the lease even if the handler raises;
- returns deterministic HTTP 503 with `Retry-After: 1` when admission is
  closed;
- preserves health probes during STARTING or DRAINING;
- uses segment-aware exemption matching so `/api/healthz` cannot accidentally
  inherit `/api/health` authority.

Backend health exemption: `/api/health`.

Engine health exemption: `/api/v1/health`.

## Engine execution supervision

The engine execution coordinator receives the engine service lifecycle directly.

For normal submissions:
1. durable command identity is validated;
2. lifecycle work admission is required;
3. an execution lease is acquired;
4. the exact local task is bound to that lease;
5. completion/cancellation releases the exact task lease.

For startup recovery, the coordinator may acquire leases while STARTING. This is
the only lifecycle admission exception and exists so durable executions can be
rehydrated before READY is advertised.

During shutdown:
1. service enters DRAINING;
2. generation cancellation is asserted;
3. new HTTP and engine execution work is rejected;
4. active coordinator tasks are cancelled/drained;
5. exact task leases are released;
6. durable dependencies are closed;
7. STOPPED is allowed only when the lease set is empty.

Coordinator lease retirement is reconciled twice: normal task callbacks release
the exact task-bound lease, and shutdown performs a deterministic post-gather
reconciliation so correctness does not depend on event-loop callback timing.
Missing/disappeared leases are recorded as supervision faults; once faulted the
coordinator refuses new execution admission. Engine dependency handles are
still closed best-effort, but cleanup faults are re-raised and lifecycle STOPPED
is not asserted.

## Connector cancellation contract

The connector inventory is derived from
`machine/ai_app_construction.json:provider_surfaces`. Every
`network_transport_owner == true` surface must appear exactly once in the
VOL-004 connector inventory. Undeclared network transports fail closed.

Each connector declares:
- cancellation mode;
- bounded timeout;
- deadline propagation where supported;
- cancellable retry waiting;
- late-result fencing;
- concrete implementation symbols.

Current governed network surfaces include the canonical engine provider runtime
and repository-automation provider transports. The backend-to-engine service
transport is additionally governed as an internal connector.

Blocking urllib-based automation connectors accept a shared
`CancellationToken`, check it before dispatch, check it after response arrival,
and use token-aware retry waits. A response that arrives after cancellation may
be observed for transport cleanup but cannot become authoritative output.

The canonical provider owner is governed at operation granularity, not by one
representative text call. The machine contract covers async text generation,
the synchronous Jeeves-compatible text adapter, image generation, image
variation, image editing, and speech synthesis. Expected operations are derived
from the active OpenAI capability declaration in
`machine/ai_app_construction.json`; the synchronous operation is additionally
required whenever that manifest declares a sync adapter.

All async provider network calls share one bounded-call primitive. An absolute
deadline is validated before the provider-call factory is invoked, so expired
work cannot perform network I/O. The same deadline bounds image and speech
operations as well as text. Timeout cancels the awaited provider task, while
external task cancellation propagates unchanged. Speech response reads are
also bounded when the SDK exposes an awaitable reader.

The synchronous provider adapter accepts a cooperative cancellation token,
checks it before architecture/network work, between retry attempts, immediately
after blocking response read, and before usage finalization. Cancellation wins
over transport retry classification; a late response is quarantined and cannot
be promoted to authoritative output.

Durable engine cancellation remains authoritative: the backend delegates
cancellation to the engine rather than inventing local terminal truth.

## Failure and race model

The contract explicitly defends against:
- cancellation before network dispatch;
- cancellation while retry backoff is sleeping;
- non-recallable upstream work returning after cancellation;
- cancellation after a supervised node becomes SUSPECT;
- restart-budget consumption after cancellation;
- stale task callbacks after a replacement task starts;
- duplicate work admission;
- STOPPED with in-flight work;
- governed AI-tree mirror drift;
- newly introduced network transports without cancellation declarations;
- health-prefix confusion;
- handler exceptions leaking work leases;
- cancellation retry changing durable terminal truth;
- expired provider work dispatching network I/O;
- media calls escaping the text-only deadline boundary;
- synchronous provider retries continuing after cancellation;
- backend daemon threads touching dependencies after STOPPED;
- coordinator lease disappearance being silently ignored;
- generated request identity depending on Python object IDs;
- provider capability growth without a corresponding supervised operation.

## Verification

The independent exact-head gate is
`.github/workflows/vol004-runtime-supervision.yml`.

It compiles the changed runtime surfaces, validates the machine contract,
requires canonical/AI mirror parity, executes lifecycle and connector
adversarial tests, exercises kernel supervisor cancellation, and re-runs the
cross-service cancellation/lease journey.

VOL-004 is not complete merely because this document or the structural validator
passes. Completion requires:
1. all implementation gaps retired;
2. exact-head focused gate success;
3. relevant repository-wide gates green on the landing head;
4. independent verification signoff in the accountability ledger;
5. completion event and masterplan checkbox only after the preceding evidence
   exists.

No queued, stale, cancelled, or inferred CI result is acceptable completion
evidence.
