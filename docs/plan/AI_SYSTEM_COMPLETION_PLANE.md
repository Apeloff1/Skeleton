# AI System Completion Plane

## Purpose

The standalone AI/SI completion program now has a system-level closure plane in
addition to atomic accountability and vertical-suite checks. The plane exists
to prevent a common false-positive: declaring the AI complete because many
subsystems are green while a cross-cutting lifecycle is still broken.

A completion verdict is therefore **non-compensable**. Sixteen requirements must
each have one passing, independently witnessed proof for the same subject and
the same exact Git revision. Extra green evidence cannot cancel a missing or
failed requirement.

## Required cross-cutting proofs

| Requirement | What must be observed |
| --- | --- |
| `execution.local_model` | A completed transaction using only local provider receipts, with a terminal output and stream identity. |
| `execution.offline_isolation` | The local transaction performs no external network I/O and all provider receipts remain local. |
| `execution.request_result_binding` | The terminal result is bound to the exact execution and operation identity requested. |
| `execution.request_result_binding` | The terminal execution/operation identities match the canonical request identity; cross-operation results cannot be substituted. |
| `execution.budget_bounds` | Observed provider/tool calls remain within the request's hard model-turn and tool-call budgets. |
| `execution.tool_authority` | Every observed tool invocation is declared by the request and has a corresponding receipt. |
| `execution.tool_authority` | Every observed tool call belongs to the request's declared tool authority and has a receipt. |
| `execution.durable_recovery` | A separately reopened execution repository yields the exact terminal result, not a best-effort reconstruction. |
| `execution.replay_lineage` | Recovered turns remain contiguous, subject/operation-bound, uniquely identified, parent-linked, and checkpoint-bound. |
| `execution.reproducibility` | A fresh repository/run using the same request and local model reproduces both terminal-result and final-output digests. |
| `execution.reproducibility` | A second deterministic local run reproduces both the terminal result digest and final-output digest. |
| `execution.governed_effects` | Every mutating tool receipt has a matching observed postcondition; read-only traffic remains valid with zero mutable postconditions. |
| `verification.independent` | The terminal result carries a passing policy-satisfied verification receipt and external evidence references. |
| `verification.claim_binding` | The verification receipt's candidate digest and context digest exactly match the published final output and request context. |
| `verification.claim_binding` | The verification receipt is cryptographically bound to the actual final candidate and context digest. |
| `context.integrity` | The context ledger has a non-genesis head and verifies its complete hash chain without link/hash errors. |
| `memory.lifecycle` | A subject-bound memory is written, retrieved, explicitly deleted, and no longer retrieved after deletion. |
| `finalization.lineage` | Completed output retains terminal stream identity plus durable memory and artifact references. |
| `learning.promotion` | A candidate is promoted only through a bound independent evaluation and becomes the active version. |
| `learning.rollback` | The promoted candidate can be rolled back to its baseline while preserving promotion/evaluation lineage. |

The canonical machine inventory is
`machine/ai_system_completion_contract.json`. The executable model is
`skeleton/ai/runtime/system_completion.py`.

## Authority model

The completion plane is intentionally non-executing. It cannot call tools,
write memory, modify model state, promote a candidate, roll back a deployment,
or fabricate missing evidence. It accepts proof from those planes, validates
that producer and verifier identities differ, binds every proof to one subject
and exact source revision, and derives a report.

The report is invalid when any of the following is true:

- a required proof is absent;
- a required proof is present but failed;
- the same requirement appears more than once;
- the proof subject differs from the report subject;
- a proof source revision differs from the report source revision;
- a proof is self-verified;
- the source revision is not an exact 40-character Git SHA.

This keeps completion authority separate from implementation authority.

## Integrated qualification

`skeleton/testing/test_ai_system_completion_plane.py` performs a real offline
qualification rather than mocking all planes independently. In one scenario it:

1. starts the canonical `FunctionalAIRuntime` with a credential-free local
   model and governed repository-read tool;
2. verifies the produced answer through an independent verification hook;
3. binds the exact request/execution/operation identities to the terminal result;
4. proves the model never leaves local provider identity and performs no external
   network I/O;
5. proves the observed tool call is inside declared authority and every observed
   call has a receipt;
6. checks observed model/tool usage against hard request budgets;
7. binds the verification receipt to the actual candidate digest and context;
8. binds memory/artifact lineage during terminal finalization;
9. reopens the SQLite execution repository and compares the full terminal
   payload exactly;
10. validates recovered turn parentage, sequence continuity, operation identity,
    and checkpoint lineage;
11. re-executes the deterministic local transaction and requires equivalent
    result/output digests;
12. appends and verifies a context-ledger block;
13. writes, retrieves, deletes, and re-queries subject-bound memory;
14. builds deterministic feedback assignments, evaluates a candidate, promotes
    it, and verifies the active version;
15. executes a rollback and verifies restoration of the baseline while retaining
    evaluation lineage;
16. submits all sixteen independently witnessed proofs to the completion plane
    and requires one terminal valid report.

Adversarial tests prove that tampered recovery, cross-operation result binding,
undeclared tool use, broken replay parentage, replay divergence, budget overrun,
network attempts, verification/candidate mismatch, self-verification, missing
requirements, mutable-effect/postcondition mismatch, source-revision drift,
duplicate proofs, and failed forgetting remain terminal blockers.

## Causal binding graph

The sixteen proofs are intentionally not a bag of independent booleans.  They
form a causal closure chain:

`request identity -> local/offline execution -> declared tool authority ->
receipts/effects -> persisted terminal result -> recovered turn/checkpoint
lineage -> deterministic fresh replay -> independently verified exact candidate
and context -> context/memory/finalization lineage -> externally evaluated
promotion -> rollback to the evaluated baseline`.

Every proof carries the same subject and exact source revision in its digest.
This prevents evidence from different commits, executions, tenants, candidates,
or learning experiments from being stitched together after the fact.  The
system report is only valid when the entire causal chain is simultaneously
closed.

## Exact-head CI

The `AI System Completion` workflow checks out the exact pull-request head,
runs the integrated qualification together with VS-001 and VS-005 regressions,
then emits an independent exact-head verifier receipt through
`scripts/verify_ai_system_completion.py`.

The verifier cross-checks:

- machine-contract requirement inventory vs runtime inventory;
- required authority controls;
- required acceptance files;
- behavioral acceptance wiring;
- workflow exact-head wiring;
- digest bindings for the contract, runtime, tests, and workflow.

The CI receipt must identify the exact Git head, contain all sixteen
requirements, carry source digests, have no errors, and have a canonical receipt
digest.

## Relationship to atomic P0-P2 work

This plane does **not** rewrite the 42-task accountability ledger and does not
turn task counts into a system-completion claim. Atomic accountability remains
useful for implementation custody. The system-completion plane answers a
different question: whether the assembled standalone AI demonstrates the
cross-cutting lifecycle required to behave as one complete system.

Likewise, the observable-effect hardening lane remains the source of truth for
the underlying mutable-effect enforcement. This completion plane consumes that
contract at the system boundary and independently refuses a completion proof
when mutable receipt counts and observed postconditions diverge.
