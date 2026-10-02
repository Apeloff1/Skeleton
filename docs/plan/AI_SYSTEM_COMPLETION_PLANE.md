# AI System Completion Plane

## Purpose

The standalone AI/SI completion program now has a system-level closure plane in
addition to atomic accountability and vertical-suite checks.  The plane exists
to prevent a common false-positive: declaring the AI complete because many
subsystems are green while a cross-cutting lifecycle is still broken.

A completion verdict is therefore **non-compensable**.  Twelve requirements must
each have one passing, independently witnessed proof for the same subject and
the same exact Git revision.  Extra green evidence cannot cancel a missing or
failed requirement.

## Required cross-cutting proofs

| Requirement | What must be observed |
| --- | --- |
| `execution.local_model` | A completed transaction using only local provider receipts, with a terminal output and stream identity. |
| `execution.offline_isolation` | The local transaction performs no external network I/O and all provider receipts remain local. |
| `execution.budget_bounds` | Observed provider/tool calls remain within the request's hard model-turn and tool-call budgets. |
| `execution.durable_recovery` | A separately reopened execution repository yields the exact terminal result, not a best-effort reconstruction. |
| `execution.replay_lineage` | Recovered turns remain contiguous, subject/operation-bound, uniquely identified, parent-linked, and checkpoint-bound. |
| `execution.governed_effects` | Every mutating tool receipt has a matching observed postcondition; read-only traffic remains valid with zero mutable postconditions. |
| `verification.independent` | The terminal result carries a passing policy-satisfied verification receipt and external evidence references. |
| `context.integrity` | The context ledger has a non-genesis head and verifies its complete hash chain without link/hash errors. |
| `memory.lifecycle` | A memory is written, retrieved, explicitly deleted, and no longer retrieved after deletion. |
| `finalization.lineage` | Completed output retains terminal stream identity plus durable memory and artifact references. |
| `learning.promotion` | A candidate is promoted only through a passing external evaluation and becomes the active version. |
| `learning.rollback` | The promoted candidate can be rolled back to its baseline through an explicit rollback receipt with a reason. |

The canonical machine inventory is
`machine/ai_system_completion_contract.json`.  The executable model is
`skeleton/ai/runtime/system_completion.py`.

## Authority model

The completion plane is intentionally non-executing.  It cannot call tools,
write memory, modify model state, promote a candidate, roll back a deployment,
or fabricate missing evidence.  It accepts proof from those planes, validates
that producer and verifier identities differ, binds every proof to one subject,
and derives a report.

The report is invalid when any of the following is true:

- a required proof is absent;
- a required proof is present but failed;
- the same requirement appears more than once;
- the proof subject differs from the report subject;
- a proof is self-verified;
- the source revision is not an exact 40-character Git SHA.

This keeps completion authority separate from implementation authority.

## Integrated qualification

`skeleton/testing/test_ai_system_completion_plane.py` performs a real offline
qualification rather than mocking all planes independently.  In one scenario it:

1. starts the canonical `FunctionalAIRuntime` with a credential-free local
   model and governed repository-read tool;
2. verifies the produced answer through an independent verification hook;
3. binds memory/artifact lineage during terminal finalization;
4. reopens the SQLite execution repository and compares the full terminal
   payload exactly;
5. appends and verifies a context-ledger block;
6. proves zero external-network attempts and checks observed model/tool usage against hard request budgets;
7. validates recovered turn parentage, sequence continuity, operation identity, and checkpoint lineage;
8. writes, retrieves, deletes, and re-queries memory;
9. builds deterministic feedback assignments, evaluates a candidate, promotes
   it, and verifies the active version;
10. executes a rollback and verifies restoration of the baseline;
11. submits all twelve independently witnessed proofs to the completion plane and
   requires one terminal valid report.

Adversarial tests also prove that tampered recovery, missing requirements,
self-verification, incomplete mutable postconditions, duplicate proofs, and
failed forgetting remain terminal blockers.

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

The CI receipt must identify the exact Git head, contain all twelve requirements,
carry source digests, have no errors, and have a canonical receipt digest.

## Relationship to atomic P0-P2 work

This plane does **not** rewrite the 42-task accountability ledger and does not
turn task counts into a system-completion claim.  Atomic accountability remains
useful for implementation custody.  The system-completion plane answers a
different question: whether the assembled standalone AI demonstrates the
cross-cutting lifecycle required to behave as one complete system.

Likewise, the observable-effect hardening lane remains the source of truth for
the underlying mutable-effect enforcement.  This completion plane consumes that
contract at the system boundary and independently refuses a completion proof
when mutable receipt counts and observed postconditions diverge.
