# VOL-007 local AI request lifecycle repair

Date: 2026-10-13 UTC
Prepared and checked by: Codex
Baseline: `714358b0e0bf285997a46f081cea5c559b33d1cb`
Scope: canonical local inference request ownership, batching and graceful shutdown.
Status: implementation and focused runtime checks complete; enterprise qualification unchanged.

## Reproduced failures

Four regression tests failed against the baseline implementation:

- `generate_many` returned a member's exception while another native worker was still running.
- One failed scheduler request failed unrelated successful requests in the same batch.
- Cancelling a scheduler submission returned before stopping its active native worker.
- A second `close` caller returned while the first caller was still draining live inference.

The repair retains all admitted work until termination, isolates batch members,
and gives each active submission its own cancellation path. Admission and close
share a lock so a producer blocked on a full queue cannot enqueue behind the
shutdown sentinel. All close callers join the same shielded shutdown task.
Repeated cancellation cannot detach cleanup.

## Construction obligations

| Level | Applied behavior or limit |
| --- | --- |
| L00 | Existing `skeleton/ai/runtime/inference/local.py` remains the owner. |
| L01 | No new service, provider, runtime root or cross-plane dependency. |
| L02 | Existing public request/result types and method signatures are preserved. |
| L03 | Admission rejects invalid request types and submissions after close. Existing provider authorization is unchanged. |
| L04 | Submission owns its inference task; cancellation propagates to native work and drains it. |
| L05 | Queue, futures and tasks remain ephemeral. Model-bound cache semantics are unchanged. |
| L06 | Independent requests cannot overwrite each other's result or failure. No network or credential boundary changes. |
| L07 | Concurrent close, cancelled close, full-queue admission and worker failure have regressions. |
| L08 | Results and exceptions remain per request; completed close now means actual worker termination. No prompt logging added. |
| L09 | Batch size and queue bounds are preserved; cancelled model work no longer continues needlessly. No throughput claim. |
| L10 | Four tests reproduce baseline failures; seven added regressions cover lifecycle and saturation. |
| L11 | No persisted schema migration. Rollback is a code revert after draining active work. |
| L12 | Stop admission via `close`, await termination, then release backend resources. Close is shared and idempotent. |
| L13 | This evidence does not promote enterprise grade or establish trained-model quality. |

## Validation

Combined local-model and offline application checks: **169 passed, 21 subtests passed**.
This includes native model activation, model identity, offline chat CLI and HTTP,
conversation persistence, local knowledge, grounding, and cancellation.

New lifecycle checks are in `skeleton/testing/test_local_inference.py` and are
already covered by `.github/workflows/p2-local-inference.yml`.

Reproduce the focused lifecycle checks:

```sh
python -m pytest -q skeleton/testing/test_local_inference.py tests/test_ai_local_inference_cancellation.py
```

The baseline assembly check and architecture, construction, capability-interface,
enterprise superiority and implementation-notes validators passed. The baseline
standalone system qualification also returned `valid: true`; that fixture result
is not proof of real-world assistant quality or complete application readiness.

## Remaining application completion work

- Run the full production frontend build and exercise every user-visible feature.
- Verify assembled services against real persisted state, including recovery.
- Qualify useful trained local weights on representative chat and game-building tasks.
- Prove Jeeves actions across editors, forges, crawlers and build/export workflows.
- Collect exact-revision deployment, performance, failure and rollback evidence.

No whole-application percentage is assigned: structural inventories and passing
subsystem tests do not supply a verified denominator of completed user journeys.

## October 23 consumer runtime repair continuation

The activated local provider now uses the existing provider boundary for
governance, finite admission and actual usage reconciliation. Its native
adapter continues to own token preparation, generation, caching and physical
worker shutdown. Ambiguous dispatched work retains conservative quota custody;
known overruns are charged and denied. Local artifact intake binds one regular
file, rejects aliases and oversized input before reading, checks descriptor and
path identity around the bounded read, and verifies source pins before parsing.

The VS-001 entry point compiles its materialized instruction, objective and
user-message inputs with the existing context compiler. The caller's source
digest remains provenance; provider context identity, digest, immutable source
snapshot and compiler version come from the compiler. Requests without an
explicit creation time start at the actual UTC time. Historical test timestamps
cannot be used as live model execution deadlines.

| Level | Applied behavior or limit |
| --- | --- |
| L00 | Existing provider, inference, artifact and context compiler owners remain authoritative. |
| L01 | `AIFT-PROVIDER-RUNTIME` remains a compatibility facade mapping; `AIFT-NATIVE-RUNTIME-ROOT` owns the native functional entry point without a parallel mirror. |
| L02 | Neutral provider types remain public. Functional execution carries the canonical compiled context fields. |
| L03 | Architecture acknowledgement, governance and finite admission precede generation; unsupported protocols are rejected. |
| L04 | Local dispatch and usage reconciliation run through the activated provider facade; native workers retain generation custody. |
| L05 | Source artifact pins, compiled snapshots and model identity are checked; no new durable store is introduced. |
| L06 | Caller context digests cannot hide changed materialized input. Symlink, inode-change and malformed artifact paths fail closed. |
| L07 | Preflight denial releases admission; ambiguous dispatched work is quarantined; cancellation drains actual workers. |
| L08 | Responses carry governance and admission receipts; failed VS-001 execution exposes the canonical terminal error code. |
| L09 | Input/output, wall time, queue, concurrency and artifact byte limits remain bounded; no throughput improvement is claimed. |
| L10 | Focused tests cover artifact intake races, usage reconciliation, protocol denial, worker cancellation and compiled-input mutation. |
| L11 | No persisted schema migration. Drain active local work before reverting the provider or functional-entry implementation. |
| L12 | Inspect local readiness and serving counters; an invalid local configuration remains unavailable without implicit hosted fallback. |
| L13 | Focused runtime evidence supports this repair only; enterprise grade and comparative superiority remain unchanged. |

Current focused evidence: the six changed coordinator, llama.cpp, native runtime,
functional handoff, effectiveness and system-completion test files have **116
passed**; offline chat fixture checks have **40 passed, 12 subtests passed**.
The complete inference manifest and assembled production
acceptance are tracked separately in the October 22 consumer-readiness run.
