# Operational AI: preflight-before-fence and real-model first-boot qualification

## Motivation and integration boundary

This pass fixes a recoverability defect: an unsuitable inference context could
reserve an operation, fail before the native backend starts, and leave a durable
`pending` request. The operational execution spine now reconstructs the
fully verified history and evaluates the current context **before** acquiring
an inference fence. Only after preflight and cancellation checks pass is a
request reserved. Errors from the native backend remain conservatively held,
since native work may already have executed before an exception was observed.

## Ordered ownership

| Wave | Work | Code ownership |
| --- | --- | --- |
| MBW-00 | Strict model/principal, token and receipt contracts | Existing spine contracts; new capacity contracts |
| MBW-01 | Atomic inference, audit, outbox, replay, fenced commit | Existing `execution_spine` transactions |
| MBW-02 | Read-only source provenance and conservative context projection | Existing knowledge plane and `capacity` planner |
| MBW-04 | Native inference planning, execution and loss-accounted receipts | `orchestration/execution_spine/capacity` and coordinator |
| MBW-07 | Operator-driven real checkpoint/restart probe | `deployment/qualification` |

The actual history is *never compacted or deleted* by capacity admission.
The plan selects complete historical user/assistant pairs, evicting oldest pairs
until capacity is available. Only then does it discard lowest-ranked whole
source excerpts. All omission counts and source hashes are included in the
committed transaction, and no discarded excerpts are silently represented as
present. The current user prompt cannot be truncated to satisfy a budget.

Backends with a trustworthy chat-template-aware `count_tokens` capability
may supply an exact count. If unavailable (including the existing GGUF
adapter), native pre-count is explicitly `unverified`. The final native
receipt still enforces its total context ceiling; no conservative byte
approximation is misrepresented as a tokenizer proof. Strict pre-count
qualification can be selected but will block unsupported backends.

## Native first-boot acceptance — requires real approved model bytes

The operator probe is executable only on a machine with the genuine
operator-approved GGUF checkpoint, its digest-pinned manifest, a private
state directory, a private report directory, and a compatible `llama_cpp`
backend. It always uses `deployment.production.startup.activate`; there is
no remote/model stub fallback in the CLI.

```bash
python -m skeleton.ai.runtime.operational_ai.deployment.qualification.cli \
  --model-root /private/approved-gguf \
  --state-dir /private/ai-state --report-dir /private/receipts \
  --report-name first-boot.json --tenant local --subject operator
```

This probe activates real model bytes, commits one prompt with native token
accounting and a durable receipt, closes all resources, reactivates from the
same private state, verifies an identical replay and the database integrity
invariants, and emits a bounded private proof with no prompt or answer text.
The probe does not assess semantic correctness, safety, license validity,
latency SLOs, target-device installation or release readiness. Injected
fixture activation is solely for tests and is marked **fixture-only**.

## Local evidence and remaining holds

- Focused capacity and qualification tests: 33 passed.
- Wider AI regression: 543 tests passed from a partial local source checkout.
- Two older test modules were excluded because `scripts/build_ai_ecosystem_bundle.py`
  and the current `orchestration.recovery.reconcile` implementation are not
  available in the partial local baseline. This is **not** a full-repo pass.
- `python -m compileall`: passed for new and modified Python modules.
- Model activation on actual operator-approved GGUF: not executed.
- Complete GitHub exact-head security, CI and device tests: not certified.
- 1.9 GB artifact: still held until actual approved model/data bytes exist.

This is source integration, not release acceptance. Draft PR remains held.

## Native flight-control admission

The loopback flight HTTP `submit` path now checks capacity before inserting a
new queued request. It returns an omission/projection digest rather than
plaintext source snippets. A duplicate previously accepted job is validated
against the original intent by the flight ledger and is replayable even if
its former evidence or context settings have since changed. This preflight is
**not** execution attestation: the worker independently re-evaluates capacity
under a session fence when it actually starts native generation. Direct
operator bulk-import paths still rely on the worker-side mandatory admission.
