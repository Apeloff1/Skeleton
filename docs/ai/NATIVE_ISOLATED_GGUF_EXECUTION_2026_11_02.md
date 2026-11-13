# Native GGUF model process isolation — AI operational execution

This changes *inference execution*, not the game plane. The existing real,
operator-approved GGUF model loader remains authoritative for model license,
manifest identity, streamed shard verification, sealed Linux anonymous image,
and in-process llama.cpp activation. `model/isolation/` adds a distinct **local
subprocess boundary** so the SQLite/HTTP supervisor does not execute potentially
blocking native C++ code in its own process.

## Actual dataflow

```
approved manifest + GGUF shards (private, externally supplied)
  -> production startup principal + model digest binding
  -> fixed local child process (no model root in public argv)
  -> validated BOOT (private length-framed pipe)
  -> child: verify manifest + all shards -> sealed memfd -> llama.cpp
  -> READY (exact model/tokenizer/manifest digests)
  -> parent: durable, session-fenced inference reservation
  -> GENERATE (strict roles, bounded text, seeded generation, no tools)
  -> child: real native Generation receipt
  -> parent: exact response/hash/token/sequence verification
  -> SQLite: atomic turn + receipt + chained audit + outbox
  -> HTTP: only committed responses, no direct model/tool privileges
```

## Critical failure behavior

- A native computation may complete before the process dies; therefore **any
  timeout, EOF, model crash, unexpected IPC sequence, output digest mismatch,
  or invalid token accounting kills and poisons the child**. The service does
  not restart it or repeat the pending request automatically. The authoritative
  queue stays pending or held for an authenticated operator to reconcile.
- `--isolate-native` selects the child backend for both `production.cli` and
  `transport.flight.serve`. This flag is opt-in during compatibility migration;
  the existing in-process path remains available but is not newly certified.
- Worker runs with sanitized environment (no provider API keys), fixed module
  import target, private anonymous stdin/stdout pipes, no shell, and a new
  process session. Public stdout of the child is reserved for the binary
  protocol. The model root is conveyed over the private pipe, not argv.
- No assertion that this is a hostile-code sandbox: same UID, filesystem
  privileges and network namespace are inherited. External model runtimes
  require isolation (container/OS policy) for hostile code and separate
  hardware/drivers qualification. No preemptive CUDA GPU reset is promised.
- The parent receives only model output, usage, and attested IDs; tool calls,
  unsupported model role, and external provider fallback are absent.
- `probe()` proves worker protocol responsiveness, not model semantics. The
  real-model `probe` CLI exercises a true GGUF and logs **only SHA-256 and
  token/timing receipts**, not prompt or generated plaintext.

## Local operator example (Linux only)

Provision real approved GGUF shards and manifest first. No artifact is copied
into ordinary Git source.

```bash
python -m skeleton.ai.runtime.operational_ai.model.isolation.probe \
  --model-root /private/approved-model --context 2048 --threads 4 \
  --max-new-tokens 128 --repetitions 3 --timeout-ms 90000

python -m skeleton.ai.runtime.operational_ai.deployment.production.cli \
  --model-root /private/approved-model --state-dir /private/ai-state \
  --tenant personal --subject operator --isolate-native \
  --prompt 'Explain your loaded model identity.'

python -m skeleton.ai.runtime.operational_ai.transport.flight.serve \
  --model-root /private/approved-model --state-dir /private/ai-state \
  --bearer-file /private/ai-state/http.bearer --tenant personal \
  --subject operator --isolate-native
```

`state-dir` must be provisioned privately according to the existing bootstrap
contract, and the bearer file is separately generated. For real-model tests:

```bash
SKELETON_TEST_APPROVED_GGUF_ROOT=/private/approved-model \
python -m unittest skeleton.testing.test_ai_isolated_native_optional -v
```

A skipped model test **does not count as passing**. The fixture-only subprocess
suite and SQLite integration tests prove protocol and custody behavior, not
real-model latency, OOM resilience, semantic capability or release readiness.
All mandatory final-head CI gates, consumer hardware checks and 1.9GB package
admission remain independent release holds.

## Measured memory admission, before the database lease

`ExecutionSpine` invokes `backend.admit_before_reservation()` when provided by
the isolated backend. The check reads Linux `MemAvailable`, the active v2
`memory.max` / `memory.current` cgroup and the live subprocess status. It
requires 128 MiB free *after* current model allocation as a conservative,
explicit lower bound. A missing/ambiguous cgroup controller, untrusted kernel
counter, dead child, or measured shortage blocks **before** a new inference
request is persisted. This is an observation, not a mathematical OOM guarantee:
GPU allocation, third-party native allocator growth, memory fragmentation,
and concurrent external load still require hardware acceptance tests.

If an inference has already started and then stalls, `close()` can kill the
worker from another thread even while `generate()` is blocked waiting for IPC.
The response is discarded, the pending database request remains held, and no
automatic retry occurs. Exactly-once model execution is not claimed across a
crash; only authoritative *commit/replay* and explicit unknown-execution holds.
