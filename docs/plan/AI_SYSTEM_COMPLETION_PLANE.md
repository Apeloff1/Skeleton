# AI System Completion Plane

## Purpose

The standalone AI/SI completion program has a system-level closure plane in
addition to atomic accountability and vertical-suite checks. Its job is to
prevent a false-positive completion verdict when many subsystems are green but
one cross-cutting lifecycle is still broken.

Completion is **non-compensable**. All eighteen requirements must have one
passing, independently witnessed proof for the same execution subject and exact
Git revision. Extra green evidence cannot compensate for a missing or failed
proof.

## Required cross-cutting proofs

| Requirement | What must be observed |
| --- | --- |
| `execution.local_model` | A completed transaction uses only local provider receipts and publishes a terminal output/stream identity. |
| `execution.offline_isolation` | Qualification performs zero AF_INET/AF_INET6 network attempts and every provider receipt remains local. |
| `execution.request_result_binding` | Terminal execution/operation identities exactly match the canonical request identity. |
| `execution.budget_bounds` | Observed provider and tool calls remain within hard request budgets. |
| `execution.stop_semantics` | An expired deadline and a durable cancellation both terminate before provider/tool work and cannot publish user-visible success. |
| `execution.tool_authority` | Every observed tool invocation is declared by the request and has a corresponding receipt. |
| `execution.durable_recovery` | A separately reopened repository yields the exact terminal result, not a best-effort reconstruction. |\n| `execution.staged_finalization_recovery` | A staged terminal intent survives repository close/reopen, finalizes to the exact result, and is cleared after recovery. |
| `execution.replay_lineage` | Recovered turns are contiguous, subject/operation-bound, uniquely identified, parent-linked, and checkpoint-bound. |
| `execution.reproducibility` | A fresh repository/run of the same deterministic local request reproduces result and final-output digests. |
| `execution.governed_effects` | Every mutating tool receipt has a matching observed postcondition; read-only traffic cannot counterfeit mutable-effect proof. |
| `verification.independent` | Terminal output carries a passing, policy-satisfied independent verification receipt plus evidence refs. |
| `verification.claim_binding` | The verification receipt candidate/context digests exactly match the published final output and request context. |
| `context.integrity` | The context ledger has a non-genesis head and verifies its complete hash chain. |
| `memory.lifecycle` | Subject-bound memory is written, retrieved, explicitly deleted, and absent after deletion. |
| `finalization.lineage` | Completed output retains terminal stream identity plus durable memory and artifact references. |
| `learning.promotion` | A candidate is promoted only through a bound external evaluation and becomes active. |
| `learning.rollback` | The promoted candidate rolls back to baseline while retaining the same evaluation lineage. |

The canonical inventory is
`machine/ai_system_completion_contract.json`. The executable proof model is
`skeleton/ai/runtime/system_completion.py`.

## Authority model

The completion plane is intentionally non-executing. It cannot grant tool
authority, write memory, modify model state, promote a candidate, or fabricate
missing evidence. It validates evidence emitted by the runtime planes.

Every proof is bound into its digest with:

- requirement identity;
- execution subject;
- exact source revision;
- producer identity;
- independent verifier identity;
- evidence references;
- observed details;
- pass/fail state.

A report is invalid if a proof is absent, failed, duplicated, self-verified,
from another execution subject, or from another source revision. Request/result,
verification candidate/context, memory ownership, and learning evaluation
lineage are also fail-closed.

## Causal closure graph

The eighteen proofs are not a bag of independent booleans. They form one
causal chain:

`request identity -> local/offline execution -> budget + stop fences ->
declared tool authority -> receipts/effects -> persisted terminal result ->
recovered turn/checkpoint lineage -> deterministic fresh replay -> independent
verification bound to exact candidate/context -> context/memory/finalization
lineage -> externally evaluated promotion -> rollback to evaluated baseline`.

This prevents evidence from different commits, executions, candidates, memory
owners, or learning experiments from being stitched into a synthetic completion
claim.

## Executable qualification

`skeleton/ai/evaluation/system_qualification.py` is the canonical executable
qualifier. It runs the assembled AI rather than only inspecting configuration.

One qualification run:

1. starts `FunctionalAIRuntime` with a credential-free local model and governed
   `repo.read` tool;
2. runs under a socket guard that rejects/counts external network attempts;
3. independently verifies the final output and binds the verification receipt to
   the exact candidate/context digests;
4. binds memory/artifact lineage during finalization;
5. checks hard model-turn/tool-call budgets and declared-tool authority;
6. independently exercises an already-expired deadline and a durable
   cancellation request, requiring both to stop before provider/tool work;
7. reopens SQLite and compares the full terminal result exactly;\n8. stages a second terminal intent, closes SQLite to simulate a crash, reopens it, finalizes the staged result, and requires the intent to clear;
8. validates recovered turn parentage, sequence, operation identity, and
   checkpoint lineage;
9. reruns the same request in a fresh SQLite repository and requires identical
   terminal-result and final-output digests;
10. appends and verifies a context-ledger block;
11. writes, retrieves, deletes, and re-queries subject-bound memory;
12. performs deterministic feedback assignment and external evaluation;
13. promotes the evaluated candidate and verifies active-version transition;
14. executes rollback and verifies baseline restoration under the same
   evaluation digest;
15. submits all eighteen proofs to `SystemCompletionPlane`;
16. emits a canonical `SystemQualificationReceipt` containing the report,
   run/replay digests, observed tool trace, network-attempt count, and receipt
   digest.

The CLI entry point is
`scripts/run_ai_system_completion_qualification.py`.

## Adversarial qualification

The acceptance suite also proves that the following remain terminal blockers:

- network escape attempts;
- request/result substitution;
- model/tool budget overflow;
- deadline or cancellation leakage into provider/tool work;
- undeclared tool use or receipt-count mismatch;
- tampered durable recovery;
- broken turn parentage/checkpoint lineage;
- nondeterministic rerun output/result;
- mutable effects without observed postconditions;
- verification receipt for a different candidate/context;
- self-verification;
- source-revision mixing;
- cross-subject memory evidence;
- missing or duplicate requirements;
- failed memory forgetting;
- promotion/rollback lineage divergence.

## Exact-head CI

The **AI System Completion** workflow checks out the exact pull-request head and
runs three layers of evidence:

1. integrated/adversarial pytest acceptance plus VS-001 and VS-005 regressions;
2. the executable qualifier, which writes
   `.ai-system-runtime-qualification.json`;
3. the independent structural verifier, which writes
   `.ai-system-completion.json`.

CI independently asserts that the executable receipt:

- is bound to the exact PR head;
- is valid with no missing/failed requirements;
- contains exactly eighteen proofs;
- has one subject and one source revision across all proofs;
- reports zero network attempts;
- reproduces result/output digests and tool trace on a fresh run;
- carries canonical report/proof/receipt digests.

The structural verifier separately checks machine-contract/runtime inventory
parity, authority controls, acceptance/qualifier bindings, workflow wiring, and
source-file digests.

## Relationship to atomic P0-P2 work

This plane does **not** rewrite the 42-task accountability ledger and does not
turn task counts into a system-completion claim. Atomic accountability remains
implementation custody; this plane answers whether the assembled standalone AI
demonstrates the required complete-system lifecycle.

The observable-effect hardening lane remains the source of truth for mutable
postcondition enforcement. System completion consumes that contract at the
assembled boundary and refuses closure when effect evidence is incomplete.
