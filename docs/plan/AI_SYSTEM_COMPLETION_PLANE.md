# AI System Completion Plane

## Purpose

The standalone AI/SI completion program has a system-level closure plane in
addition to atomic accountability and vertical-suite checks. Its purpose is to
prevent false completion claims when individual subsystems pass but the
assembled lifecycle, security boundary, persistence path, or learning path is
still broken.

Completion is **non-compensable**. All thirty-two requirements must have one
passing, independently witnessed proof for the same execution subject and the
same exact Git revision. Extra green evidence cannot compensate for a missing
or failed proof.

The canonical inventory is
`machine/ai_system_completion_contract.json`. The executable proof model is
`skeleton/ai/runtime/system_completion.py`.

## Thirty-two required proofs

### Execution and recovery

| Requirement | Required observation |
| --- | --- |
| `execution.local_model` | A completed transaction uses only local provider receipts and publishes terminal output and stream identity. |
| `execution.offline_isolation` | Qualification performs zero external socket attempts and all provider receipts remain local. |
| `execution.request_result_binding` | Terminal execution and operation identities match the canonical request. |
| `execution.budget_bounds` | Model-turn and tool-call usage remains inside hard request budgets. |
| `execution.stop_semantics` | Deadline and durable cancellation both stop before provider/tool work and cannot publish success. |
| `execution.tool_authority` | Every observed tool call was declared by the request and has a receipt. |
| `execution.durable_recovery` | Reopening SQLite yields the exact terminal result. |
| `execution.staged_finalization_recovery` | A staged terminal intent survives close/reopen, finalizes exactly once, and clears its intent. |
| `execution.replay_lineage` | Recovered turns remain contiguous, subject/operation-bound, unique, parent-linked, and checkpoint-bound. |
| `execution.reproducibility` | A fresh repository run reproduces terminal-result and final-output digests. |
| `execution.governed_effects` | Every mutable effect has a matching observed postcondition. |

### Verification, context, and durable state

| Requirement | Required observation |
| --- | --- |
| `verification.independent` | Terminal output carries a passing independent verification receipt and evidence references. |
| `verification.claim_binding` | Candidate and context digests in the verification receipt exactly match the published output and request context. |
| `context.integrity` | The context ledger has a non-genesis head and a valid complete hash chain. |
| `memory.lifecycle` | Subject-bound memory is written, recalled, deleted, and absent after deletion. |
| `finalization.lineage` | Terminal output retains stream identity plus durable memory and artifact references. |

### Persistence, delivery, and accounting integrity

| Requirement | Required observation |
| --- | --- |
| `persistence.terminal_evidence_integrity` | Mutable execution state, turns, checkpoints, terminal results, and outbox payloads carry independent persisted digests; contract-valid tampering fails closed; legacy stores backfill safely; and a hash-chained execution-state journal proves mutation continuity. |
| `verification.receipt_identity` | Identical verification-receipt replay is stable, conflicting identity replay is rejected, persisted receipt tampering is detected, and execution/result binding remains intact. |
| `finalization.outbox_delivery` | Exactly one terminal event is pending, acknowledgement survives reopen, retry acknowledgement is stable, and no event remains pending after acknowledgement. |
| `resource.unknown_usage_fence` | Unknown actual usage is recorded durably; completion and release are blocked until conservative usage resolution is supplied. |

### Hostile-environment security

| Requirement | Required observation |
| --- | --- |
| `security.sandbox_filesystem` | Filesystem jail permits safe round-trip I/O while rejecting traversal and preserving outside state. |
| `security.sandbox_process` | Subprocess execution has a scrubbed environment, rejects shell-string execution, stays bounded, and fails closed on network isolation. |
| `security.injection_sanitization` | Prompt and shell attacks are detected, secrets are redacted, and duplicate-key JSON is rejected. |
| `privacy.provider_fallback` | Provider routing cannot cross the request privacy boundary even when the permitted provider is unhealthy. |
| `memory.poisoning_resistance` | Governed memory accepts a valid provenance-bound write while rejecting missing provenance and conflicting proposal replay. |
| `security.outbound_network_boundary` | Private targets, mixed public/private DNS answers, and peer rebinding are rejected while canonical public resolution succeeds. |

### Resource, retry, and tenant boundaries

| Requirement | Required observation |
| --- | --- |
| `resource.admission_quota` | Work inside budget is admitted, over-quota work is rejected without consuming capacity, and actual usage reconciles against the reserved quota. |
| `resource.shared_pressure` | Two independent workers cannot overbook one shared concurrency scope, and capacity becomes available only after the first lease completes. |
| `execution.idempotent_retry` | Identical admission retry returns the same lease without double reservation, while conflicting retry inputs fail closed. |
| `privacy.tenant_isolation` | Durable memory is visible only inside the owning tenant/subject authority scope and cross-tenant lookup fails closed. |

### Learning lifecycle

| Requirement | Required observation |
| --- | --- |
| `learning.promotion` | Promotion is bound to the qualified result and an external evaluation; failed or cross-experiment evaluation is rejected. |
| `learning.rollback` | Rollback restores baseline under the same evaluation lineage and rollback without prior promotion is rejected. |

## Authority model

The completion plane is non-executing. It cannot grant tool authority, mutate
memory, alter model state, promote a candidate, or fabricate missing evidence.
It consumes observations from the owning planes and produces a fail-closed
report.

Every proof digest binds:

- requirement identity;
- execution subject;
- exact source revision;
- producer identity;
- independent verifier identity;
- evidence references;
- observed details;
- pass/fail state.

The report rejects missing, failed, duplicate, self-verified, cross-subject, or
cross-revision proofs. Applicable source objects must themselves belong to the
same execution; merely relabeling evidence does not satisfy completion.

## Causal closure graph

The thirty-two proofs form one causal chain rather than a bag of booleans:

`request identity -> local/offline execution -> budgets + stop fences -> tool
authority -> effects/postconditions -> durable terminal state -> crash recovery
-> replay lineage -> deterministic fresh replay -> independent exact-claim
verification -> context/memory/finalization lineage -> hostile-environment
sandbox/privacy/network checks -> result-bound learning promotion -> rollback`.

Evidence from another commit, execution, provider boundary, memory owner,
candidate, or learning experiment cannot be stitched into a valid completion
claim.

## Executable qualification

`skeleton/ai/evaluation/system_qualification.py` runs the assembled system.
The CLI entry point is
`scripts/run_ai_system_completion_qualification.py`.

A qualification run performs all of the following on one exact source revision:

1. executes `FunctionalAIRuntime` with a credential-free local model and
   governed `repo.read`;
2. denies and counts external socket attempts;
3. binds verification to the exact candidate and context;
4. binds deterministic memory/artifact lineage at finalization;
5. enforces hard model/tool budgets and declared tool authority;
6. exercises already-expired deadline and durable-cancellation paths;
7. reopens SQLite and compares the terminal result exactly;
8. stages a second terminal intent, simulates restart, finalizes it, and proves
   the durable intent is cleared;
9. integrity-binds terminal result/outbox rows, rejects contract-valid persisted
   payload tampering, and verifies legacy digest backfill;
10. proves verification-receipt identity is retry-stable and conflict/tamper
    fail-closed;
11. acknowledges the durable terminal outbox, reopens persistence, and proves
    acknowledgement retry stability;
12. validates turn ancestry, operation identity, and checkpoint lineage;
10. reruns the same request in a fresh repository and compares output/result
    digests and tool traces;
11. verifies a context-ledger block;
12. performs memory write, recall, delete, and absence;
13. exercises the filesystem jail against traversal;
14. executes a bounded sandbox subprocess with environment scrubbing and
    fail-closed network policy;
15. attacks prompt/shell sanitization, secret redaction, and strict JSON;
16. forces provider routing under a local-only privacy boundary while the local
    provider is unhealthy;
17. performs governed-memory success, missing-provenance rejection, and
    conflicting-replay rejection;
18. exercises private-target, mixed-DNS, and peer-rebinding network defenses;
23. admits in-budget work, rejects tenant over-quota work, and reconciles actual usage;
24. records deliberately unknown usage and proves completion/release remain
    fenced until conservative resolution;
25. proves two workers cannot overbook one shared-pressure scope;
26. proves identical retry is idempotent while conflicting retry is rejected;
27. writes tenant-scoped durable memory and proves cross-tenant invisibility;
28. runs evaluation, promotion, and negative promotion gates;
29. rolls back and proves evaluation lineage is preserved;
30. submits all thirty-two proofs to `SystemCompletionPlane`;
31. emits one canonical machine-readable qualification receipt.

## Independent receipt verification

`scripts/verify_ai_system_qualification_receipt.py` is a separate verifier.
It does not trust the qualifier's stored `valid` flags or digests.

It reparses the emitted receipt with duplicate-key rejection, recomputes every
proof digest, recomputes the system-completion report digest, recomputes the
top-level qualification digest, and independently evaluates the **semantics of
all thirty-two proof types** from serialized evidence.

This means a proof cannot survive by changing its details, setting
`passed=true`, and recomputing every nested digest. A semantically
contradictory but cryptographically self-consistent receipt still fails.

Persistence uses the same principle internally. The authoritative execution
repository integrity-binds the current state row, each turn, each checkpoint,
terminal result, verification receipt, finalization intent, and outbox payload.
In addition, every state mutation appends a hash-chained execution-state journal
event containing the full post-mutation state snapshot and its parent digest.
Journal verification checks both cryptographic continuity and mutation
semantics for create, transition, cancellation, turn append, checkpoint, and
finalization. Legacy databases receive an explicit `migration_snapshot` root
rather than fabricated historical events.

## Exact-head CI

The **AI System Completion** workflow checks out the exact pull-request head and
runs:

1. assembled completion and adversarial acceptance;
2. VS-001 standalone-AI regression;
3. VS-005 self-improvement regression;
4. sandbox isolation and injection/sanitization regressions;
5. provider privacy-fallback regressions;
6. governed-memory writeback regressions;
7. outbound URL/HTTP security regressions;
8. admission/quota/shared-pressure and execution-repository regressions;
9. executable thirty-two-plane qualification;
10. independent cryptographic and semantic receipt verification;
11. structural contract/runtime/workflow verification.

CI requires all thirty-two proofs on one subject and exact revision, zero
network attempts during the local qualification, deterministic fresh replay,
complete crash recovery, hostile-environment security closure, and valid
independent verifier receipts.

## Relationship to atomic P0-P2 work

This plane does not rewrite task ledgers and does not turn task counts into a
system-completion claim. Atomic accountability remains implementation custody.
The completion plane answers whether the assembled standalone AI demonstrates
the complete cross-cutting lifecycle on the exact integrated code under test.
