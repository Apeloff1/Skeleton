# Durable AI inference flight control: no blind replay

This is an AI-only addition. It does **not** implement a game, ship a model,
qualify a model, or claim native inference has run in CI. The real model is
activated through the existing `deployment.production.startup.activate` path,
which independently validates GGUF provenance, model/tokenizer identity,
private state and the native inference backend. Failures stop at startup.

## Executable contract

1. `FlightSpec` binds tenant, subject, exact model/tokenizer, session,
   request ID, prompt, generation settings and priority to a durable digest.
2. `FlightLedger` submits in the authoritative private SQLite instance and
   creates an atomic hash-chained transition record plus outbox event. Exact
   duplicate submissions replay; conflicting request IDs do not.
3. A worker claims one job with a monotonically incremented fencing token,
   kernel boot ID and bounded monotonic lease. Claims for sessions with active
   work are excluded. Two independently running workers cannot both start
   an already-claimed job through the queue.
4. Before model execution, `claimed -> running` commits atomically. A worker
   uses `ExecutionSpine` for the actual native generation, durable receipt,
   audit and context. The local heartbeat renews *only* an active lease with
   matching worker, boot and fence.
5. Completion is accepted **only** after reading the exact request-bound,
   already committed authoritative receipt back from `ExecutionSpine`.
   Passing a fabricated output dictionary to the queue is insufficient.
6. The queue refuses implicit retries of running or expired native requests.
   A crashed or timed-out worker may have generated output. An authorized
   operator can reconcile the job from an already committed receipt; if no
   receipt exists, the job is held for manual review and a fresh request ID.
   No inference occurs during reconciliation.
7. A lease that was merely claimed but never marked running can be requeued
   *after* operator approval, invalidating the stale fence before reuse.
8. Pausing admission is persistent. It blocks new claims, does not cancel
   in-flight model executions, and does not grant new model privileges.
9. `doctor`, `watchdog`, and integrity proof exports are bounded read-only
   inventories. Their outputs omit user prompt text and secrets.

## Production CLI

The following commands require an independently installed, license-approved,
model-digest-pinned local GGUF and native backend. None substitute a mock.

```bash
# New private principal-bound session + durable admission (prompt via stdin).
python -m skeleton.ai.runtime.operational_ai.orchestration.flight_control.cli \
  submit --model-root /approved/model --state-dir /private/ai \
  --tenant owner --subject operator --new-session \
  < /private/prompt.txt

# Execute at most 16 admitted jobs with the same pinned model.
python -m skeleton.ai.runtime.operational_ai.orchestration.flight_control.cli \
  work --model-root /approved/model --state-dir /private/ai \
  --tenant owner --subject operator --maximum 16

# Read-only integrity; review queued, expired and held work.
python -m skeleton.ai.runtime.operational_ai.orchestration.flight_control.cli \
  doctor --model-root /approved/model --state-dir /private/ai \
  --tenant owner --subject operator --maximum 256

# Explicit recovery only; never reruns the model.
python -m skeleton.ai.runtime.operational_ai.orchestration.flight_control.cli \
  recover --model-root /approved/model --state-dir /private/ai \
  --tenant owner --subject operator --maximum 64 --approve
```

Run only from a trusted owner-controlled shell. The operator approval flag
is NOT authentication for remote HTTP callers; this CLI must never be exposed
as an AI-callable tool, auto-approved action, or unauthenticated web endpoint.

## Known holds and qualification

- Linux `/proc` and kernel boot ID are required. Windows/macOS need a
  separately reviewed custody implementation; do not quietly downgrade.
- The queue is local-node authoritative. It does not provide distributed
  consensus or lease fencing across unrelated storage systems.
- Native inference cannot be rolled back after GPU execution. A crash after
  generation but before the authoritative commit produces an **uncertain**
  request which must be reviewed, not retried automatically.
- The event ledger is tamper-evident against ordinary corruption; it is not an
  externally signed or write-privilege-resistant audit root.
- A 1.9 GB **real** package still requires operator-approved model/data bytes.
- Production qualification requires real-model generation, first-install,
  cross-process tests on the target machine, exact-head CI and all security
  gates; fixture-backed tests alone are insufficient.

## Focused tests

```bash
python -m unittest skeleton.testing.test_ai_execution_spine \
  skeleton.testing.test_ai_flight_control -v
python -m compileall -q skeleton/ai/runtime/operational_ai/orchestration
```
