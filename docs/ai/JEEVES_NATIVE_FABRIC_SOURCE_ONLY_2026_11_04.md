# Jeeves native operational assurance fabric

## Ownership

This is a deliberately non-provider host-side package under
`skeleton/jeeves/native_fabric`. It composes the existing local
`ActiveModel`, source-verified installer, `SupervisedAI` and private
`ExecutionSpine`; it does not introduce another inference backend or
transaction authority. All source-only policy verdicts are bounded, typed,
principal-scoped and fail closed. A green policy check is **not** GGUF model
acceptance, an independent rights approval or device readiness.

## Production-critical components

- `contracts`: typed scopes, strict finite numeric/string/JSON input and
  explicit operator-approval receipts, no implied model permission
- `budgets`: conservation-checked reservation, no inference retries, no
  automatic refund of ambiguous effects
- `events`: bounded contiguous hash-chain auditing with retained anchors,
  explicitly not an authenticated signature or KMS ledger
- `plans`: deterministic topological scheduling, CAS graph revisions,
  non-idempotent unknown-effect fencing
- `context`: source SHA receipts, trust-tier ordering, mandatory evidence,
  explicit omission accounting, no false zero-context-loss claims
- `retrieval`: lexical BM25 and deterministic UTF-8 byte-safe chunking,
  provenance remains subject to the original signed-source checks
- `citations`: exact-span source/quote hash and tenant scope checking, no
  false semantic-truth certification
- `evaluation`: independent objective tests against authoritative native
  output digests, no LLM-as-judge route
- `health`, `device`: finite and fresh telemetry, missing/unknown values
  are holds, not guessed passes
- `model_inventory`: installed-vs-active identity reconciliation and
  explicit missing physical model/device qualification
- `assurance`: final-head mandatory GitHub gate reconciliation that does
  not count stale, source-only, failed, pending, skipped or cancelled as passes
- `qualification`: aggregate readiness holds across CI, device,
  runtime, model and independent source-rights review
- `native_bridge`: read-only binding to the existing production worker;
  no alternative model loader or mutable model state
- `operator_cli`: stdin-bound offline policy and device reports, never
  starts a GGUF or fetches private content

## Operator examples (on the approved laptop)

```bash
python -m skeleton.jeeves.native_fabric.operator_cli --mode observe

python -m skeleton.jeeves.native_fabric.operator_cli \
  --mode gates --json-stdin < checked-final-head-gates.json

python -m skeleton.jeeves.native_fabric.operator_cli \
  --mode device --json-stdin < operator-observed-device.json

python -m skeleton.jeeves.native_fabric.operator_cli \
  --mode model --json-stdin < source-approved-model-records.json
```

The source-only policy CLI accepts explicit operator-produced JSON data;
it cannot independently verify that a JSON field marked `native_loaded`,
`source_rights_approved` or `host_device_attested` is truthful. Only
the native activation and real-device acceptance lanes can make those claims
with relevant external receipts. The native bridge fingerprints worker
status and resource ceilings but does not perform inference.

## Existing draft and release holds

This work is stacked on PR #4699 within draft PR #4700. The native agent
and its durable SQLite/memory layer remain subject to the physical GGUF
acceptance, Windows 11/WSL2 install, isolated in-flight cancellation,
RAM/VRAM pressure, rights review, exact-head security gates and independent
production-user qualification. Do not merge or release based on these
source-only contracts alone.

## Host-side fair native traffic gate

`native_fabric.traffic` provides bounded priority ordering, per-scope
concurrency ceilings, fair cohort rotation, terminal receipt identity and
cross-thread synchronization for admission scheduling. An ambiguous model
call remains held and consumes capacity until independent recovery; the
queue never silently retries or refunds it. This queue is **in-process**
and is explicitly NOT the already durable SQLite execution spine. It must
not be used as the authority for exactly-once inference or automatic
cross-process supervision.

## Integrated admitted native task execution

`NativeFabricSupervisor` composes a host-owned fair traffic queue,
conservation-checked resource ledger, hash-linked audit journal and the
existing `NativeBatchConveyor`. Admission checks happen before the first
model generation. Each admitted task receives one immutable canonical
SQLite session/request identity; response and replay verification remain
in the production `SupervisedAI` and `ExecutionSpine` hierarchy.

Native uncertainty retains queue capacity and the resource reservation.
A source-only test exercises the true protected SQLite/WAL path using a
**synthetic** model backend and verifies the final hash receipt, no duplicate
native call on a cold replay, principal isolation and no unauthorized tools.
In-memory audit/queue/budget state are intentionally not claimed to survive
process death; only the independently verified canonical native SQLite
receipts do. Multi-lane device-pressure qualification remains a release hold.
