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
