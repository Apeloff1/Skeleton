# Reverse-Engineering Pass: End-State Proof Graph

Status: **ACTIVE / depth pass**
Scope: deepen the breadth-frozen master plan without adding top-level architecture.
Authority: subordinate to `MASTER_PLAN.md`, current runtime contracts, signed accountability, and the canonical master build sequence.

## Why this pass exists

The forward master plan answers **what must be built** and **in what dependency-aware waves**. This pass asks the inverse question:

> If Skeleton is claimed to be complete, safe, useful, recoverable, and release-ready, what observable evidence must exist immediately before that claim, and what must exist immediately before each of those proofs?

A target is not accepted because its components exist. It is accepted only when the target can be walked backward through an acyclic chain of executable evidence to current authoritative contracts and durable state.

## Reverse-engineering laws

1. **Start from externally observable success.** Reverse chains begin at user/operator/release outcomes, not module names.
2. **Every terminal claim needs an acceptance witness.** A witness is an executable or inspectable fact that would be difficult to fake with stubs.
3. **Every witness needs a failure oracle.** The plan must state what concrete observation proves the target is not satisfied.
4. **Trace backward to authoritative state.** UI, streams, caches, model confidence, prose, and planned tests are not terminal proof.
5. **No self-certifying subsystem.** A generator, router, tool, agent, installer, or release pipeline cannot be its own sole verifier.
6. **No hidden prerequisite.** If a terminal outcome depends on security, recovery, migration, observability, policy, compatibility, or rollback, that dependency is explicit.
7. **No proof by file existence.** A path or class is implementation evidence only when coupled to behavior and acceptance evidence.
8. **No proof by happy-path only.** Each chain contains at least one negative, fault, restart, adversarial, or rollback oracle appropriate to its risk.
9. **Promotion readiness is stricter than construction readiness.** Product/UI work may proceed early; hardened/production claims wait for the reverse chain to close.
10. **Reverse constraints may narrow overlap, never widen authority.** Existing wave overlap is permitted only where downstream proof does not assume an unfinished upstream invariant.
11. **Every shortcut is named.** Stubs, mocks, bypass flags, silent fallbacks, manual toggles, and unverifiable assertions are listed where they could counterfeit completion.
12. **Breadth remains frozen at VOL-420.** Reverse engineering deepens existing volumes/work packages and does not create a parallel architecture.

## Reverse method

For each terminal outcome:

```text
terminal outcome
  <- acceptance witness
      <- postcondition proof
          <- runtime behavior
              <- capability contracts
                  <- durable authority / state semantics
                      <- canonical architecture + plan authority
```

At every edge ask:

- What must already be true?
- Which artifact is authoritative?
- Which independent observation proves it?
- What failure would falsify it?
- Can a mock/stub/cache/manual action make the proof appear green?
- What happens after restart, retry, cancellation, partial failure, migration, and rollback?
- Which earlier wave owns the invariant?

## Reverse terminal chains

### REV-00 — A user can complete a useful AI operation end to end

**Terminal outcome:** A real user objective enters a product surface and produces a durable, attributable result or artifact.

**Acceptance witnesses**
- Product request resolves to a durable operation identity.
- Operation state survives restart and can be reconstructed independently of the stream/UI.
- Context, model, tool/agent decisions, verification, artifact/result, and terminal state are attributable.
- Cancellation and deadline behavior are observable and terminal.
- A completed operation can be replay-audited without hidden reasoning text.

**Must already be true**
`MBW-05 <- MBW-04 <- {MBW-02, MBW-03} <- MBW-01 <- MBW-00`.

**Failure oracles**
- UI says complete while durable operation is nonterminal.
- Stream loss makes the operation unknowable.
- Result cannot name its model/tool/evidence/provenance chain.
- Cancellation returns success but work continues.
- Restart loses objective, authority, result, or receipt state.

**Forbidden shortcuts:** UI-only completion, ephemeral in-memory authority, fake progress events, hard-coded success results, direct provider calls bypassing operation/context/policy.

### REV-01 — A privileged tool action is safe and exactly attributable

**Terminal outcome:** A model/agent-requested side effect occurs only under valid authority and produces a durable receipt with verified postconditions.

**Acceptance witnesses**
- Proposal and authorization are distinct records.
- Authorization is evaluated on normalized inputs and current scope.
- Idempotency/compensation behavior is exercised under timeout and retry.
- Tool output cannot grant new authority.
- Postcondition verification is independent of generator confidence.

**Must already be true**
`MBW-03 <- MBW-01 <- MBW-00`, with governed context from `MBW-02` when model-originated.

**Failure oracles**
- Same request can produce duplicate external side effects.
- Authorization is inferred from tool description/model output.
- Path/URL/process target changes meaning after authorization.
- Unknown timeout outcome is retried blindly.
- Tool result marks itself verified.

**Forbidden shortcuts:** allow-all policy, bypass flags in production, non-durable receipts, verify-by-echo, mock-only security evidence.

### REV-02 — Durable continuity and memory are trustworthy after failure

**Terminal outcome:** Conversation/project continuity survives restart, restore, deletion, and stale-projection scenarios without resurrecting or silently corrupting state.

**Acceptance witnesses**
- Authoritative stores restore before projections.
- Projection rebuild is deterministic and idempotent.
- Memory promotion preserves provenance, scope, retention, contradiction handling, and deletion semantics.
- Restore/delete interaction is tested.
- Stale derived stores cannot overwrite authoritative state.

**Must already be true**
`MBW-02 <- MBW-01 <- MBW-00`, plus recovery obligations in W19.

**Failure oracles**
- Deleted data reappears after restore.
- Vector/search cache becomes source of truth.
- Memory survives without provenance or scope.
- Duplicate/out-of-order events change final state.
- Conversation continuity depends on provider-native objects.

**Forbidden shortcuts:** cache-as-authority, restore without drill, memory writes directly from model text, migration without rollback.

### REV-03 — Evidence-grounded reasoning remains bounded and policy-preserving

**Terminal outcome:** A response or plan that claims evidence support can enumerate trusted sources and retain immutable policy under context pressure.

**Acceptance witnesses**
- Retrieval/knowledge results retain source, time, scope, trust, and authorization metadata.
- Context truncation/compression preserves immutable instructions ahead of untrusted content.
- Contradictory evidence is represented rather than silently collapsed.
- Search/retrieval loops obey explicit budgets and stopping policy.
- Verification status is separate from model confidence.

**Must already be true**
`MBW-04 <- MBW-02 <- MBW-01 <- MBW-00`, with independent verification from `MBW-03`.

**Failure oracles**
- Retrieved text can self-promote to instruction authority.
- Citation points to a source that did not support the claim.
- Context pressure drops policy before low-trust content.
- Search loops until external timeout.
- Confidence score substitutes for evidence verification.

**Forbidden shortcuts:** fabricated citations, trust-by-source-name, unbounded retries, self-verification by same generation path.

### REV-04 — Multi-agent execution cannot escalate authority or collide silently

**Terminal outcome:** Specialized agents can collaborate on long-running work while preserving parent authority, ownership, budgets, and conflict safety.

**Acceptance witnesses**
- Child authority is mechanically proven to be a subset of parent authority.
- Delegation depth/fan-out/budget is bounded.
- Shared-resource mutation uses leases/fencing or equivalent ownership control.
- Handoffs carry objective, state, evidence, remaining budget, and acceptance criteria.
- Disagreement resolution leaves an attributable decision record.

**Must already be true**
`MBW-04 <- MBW-03 <- MBW-01 <- MBW-00`, with context/model substrate from `MBW-02`.

**Failure oracles**
- Child obtains broader tool scope than parent.
- Two agents can commit conflicting writes without detection.
- Agent crash loses ownership/lease semantics.
- Delegation recursively expands without hard budget.
- Supervisor accepts a result with no evidence packet.

**Forbidden shortcuts:** role-name authorization, shared mutable scratch state as authority, unlimited delegation, last-writer-wins for privileged changes.

### REV-05 — A release/install/update can be trusted and rolled back

**Terminal outcome:** A user can install or update a signed build, verify its provenance, pass first-run health, and recover to a known-good version after failure.

**Acceptance witnesses**
- Build inputs and produced binaries/artifacts are traceable.
- Installer/update packages are integrity/signature checked before activation.
- Migration is versioned and rollback/forward-recovery semantics are explicit.
- First-run health validates the actual runtime spine, not only package presence.
- Rollback is tested after partial activation/migration failure.

**Must already be true**
`MBW-07 <- {MBW-05, MBW-06} <- {MBW-04, MBW-03, MBW-02} <- MBW-01 <- MBW-00`.

**Failure oracles**
- Unsigned/untrusted package can activate.
- Update failure leaves mixed incompatible versions.
- Installer succeeds while runtime cannot complete VS-000/VS-001 class operations.
- Rollback restores binary but not schema/config compatibility.
- Release cannot identify source/build/test provenance.

**Forbidden shortcuts:** package-exists checks, manual version edits, unsigned emergency path, migration without recovery proof.

### REV-06 — Research/forge/learning cannot mutate production without comparative evidence

**Terminal outcome:** A candidate model/prompt/router/policy/code/configuration reaches production only after reproducible evaluation and explicit promotion.

**Acceptance witnesses**
- Candidate identity and parent/baseline are immutable.
- Dataset/benchmark versions and contamination checks are recorded where relevant.
- Challenger comparison reports uncertainty and regressions, not just aggregate wins.
- Security/reliability regressions are promotion blockers.
- Production activation is a separate authorized event.

**Must already be true**
`MBW-06 <- {MBW-02, MBW-03, MBW-04} <- MBW-01 <- MBW-00`; production activation additionally depends on `MBW-07`.

**Failure oracles**
- Research branch writes production state directly.
- Candidate evaluates on mutable/unversioned data only.
- Champion/challenger decision cannot be reproduced.
- Aggregate score hides critical regression.
- Learning signal changes policy without audit/promotion.

**Forbidden shortcuts:** auto-promote-on-score, production mutation from experiment process, unverifiable benchmark claims, undocumented prompt/config drift.

### REV-07 — Provider routing remains private, bounded, and recoverable

**Terminal outcome:** Model/provider fallback can occur without changing privacy/authority semantics or corrupting durable operation state.

**Acceptance witnesses**
- Provider-native types terminate at adapters.
- Routing decision records policy, budget, capability, and privacy constraints.
- Fallback cannot widen data residency/scope.
- Timeout ambiguity does not duplicate tool/action effects.
- Provider outage degrades explicitly and observably.

**Must already be true**
`MBW-02 <- MBW-01 <- MBW-00`, constrained by policy/security in `MBW-03`.

**Failure oracles**
- Fallback silently sends restricted data to an ineligible provider.
- Provider object is serialized into canonical state.
- Retry duplicates inference-linked action.
- Provider failure is surfaced as fabricated success.
- Cost/deadline budget is ignored during fallback.

**Forbidden shortcuts:** “any healthy provider” fallback, provider SDK objects in persistence, silent privacy downgrade.

### REV-08 — Operators can diagnose, repair, and recover the system without guessing

**Terminal outcome:** A production incident can be traced from user-visible symptom to authoritative operation/state/component evidence and resolved through tested repair/recovery paths.

**Acceptance witnesses**
- Correlation identity spans API, operation, model, tool, worker, artifact, and verification records.
- Health/readiness distinguishes degraded dependencies from healthy process existence.
- Support/doctor output is evidence-bearing and secret-safe.
- Recovery/repair paths are tested and bounded.
- SLO/error-budget signals can identify sustained failure.

**Must already be true**
`MBW-05 <- MBW-01 <- MBW-00`, with security constraints from `MBW-03` and production hardening from `MBW-07`.

**Failure oracles**
- Incident cannot map UI/request to durable operation.
- Health endpoint is green while core dependency is unusable.
- Repair mutates state without plan/receipt/rollback.
- Support bundle leaks secrets.
- Recovery depends on undocumented operator memory.

**Forbidden shortcuts:** process-up == healthy, log-only authority, destructive repair without snapshot/rollback, secret-rich diagnostics.

### REV-09 — Masterplan completion cannot be counterfeited

**Terminal outcome:** A completion claim can be traced from checked ledger state to independent, commit-bound, timestamped evidence and to the exact requirement it closes.

**Acceptance witnesses**
- Completion checkbox is derived from signed implementation + independent verification.
- Evidence references bind to a full commit SHA and concrete test/eval/artifact.
- Every critical/high obligation has owner and disposition.
- Planned tests are never treated as passing evidence.
- Human and machine plan mirrors agree on scope and authority.

**Must already be true**
`MBW-00` authority plus the existing accountability, edge-case, queue, and build-sequence contracts.

**Failure oracles**
- Checkbox can be manually edited to green.
- Same signer supplies implementation and verification without signed exception.
- Evidence references nonexistent/planned-only tests.
- Requirement has no owning work package/wave.
- Breadth expands past VOL-420 without ADR.

**Forbidden shortcuts:** manual completion, retroactive fabricated signature, prose-only acceptance, LOC/commit count as completion.

## Cross-chain reverse constraints

### RC-01 — Bootstrap closure
The validator/control plane needed to prove later waves must itself be buildable and testable from the early authority/runtime substrate. No late-stage service may be the only means of proving an early-stage invariant.

### RC-02 — Independent-verifier separation
Where a target can cause side effects, mutate policy, promote candidates, or mark completion, its acceptance path must include a verifier/control surface that cannot be rewritten by the target during the same transaction.

### RC-03 — Restart equivalence
For durable workflows, success before restart and success after process restart must converge to equivalent authoritative terminal state, modulo explicitly documented transient telemetry.

### RC-04 — Unknown-outcome handling
Any external request that can commit before acknowledgement must have idempotency, reconciliation, or explicit “unknown” terminal/recovery semantics. Blind retry is forbidden.

### RC-05 — Promotion barrier
Construction overlap may not be interpreted as promotion overlap. A downstream component may be developed against a stable slice of an upstream contract, but hardened/production promotion waits for the complete reverse chain and signed evidence.

### RC-06 — Migration symmetry
Every schema/protocol/config migration that can make old software unable to read new state must name forward, rollback, and mixed-version behavior or explicitly declare rollback impossible with a tested forward-recovery plan.

### RC-07 — Projection humility
Search indexes, vectors, caches, UI projections, streams, dashboards, and model context are rebuildable views unless a specific canonical contract says otherwise.

### RC-08 — Negative-space proof
For each high-impact capability, prove at least one important thing that **cannot** happen: unauthorized action, authority escalation, duplicate effect, stale overwrite, unsigned activation, policy loss, secret leak, or false completion.

## Assembly-order corrections derived by working backward

1. **Treat MBW-00/01 as semantic substrate, not “mostly done” setup.** Downstream work may overlap only on frozen contract slices; promotion blocks on unresolved authority/state ambiguity.
2. **Pull verification/security acceptance earlier than autonomy.** Tool/agent/cognition construction can proceed, but no autonomous side effect is considered usable until REV-01 closes.
3. **Treat evaluation as a release dependency, not merely an R&D plane.** A UI or runtime can be functionally complete while still not promotion-ready.
4. **Make recovery part of feature acceptance.** A durable feature is incomplete until restart/restore behavior is known.
5. **Make installer success depend on a real vertical-slice smoke proof.** Package creation alone is not an installation witness.
6. **Separate “provider fallback works” from “fallback is allowed.”** Routing success must preserve privacy, scope, budget, and deadline constraints.
7. **Do not let observability substitute for authority.** Telemetry explains canonical state; it does not define it.
8. **Require proof against counterfeit completion.** Every terminal chain includes a shortcut that validators/tests must make difficult or impossible.

## Minimum proof bundles

A terminal chain may be promoted only with a bundle containing, as applicable:

- requirement/work-package/wave IDs;
- exact commit SHA;
- test/eval command and result;
- negative/fault/restart/adversarial evidence;
- authoritative state or receipt reference;
- migration/rollback evidence where state changes;
- security/privacy disposition where data or privilege crosses a boundary;
- independent verifier identity;
- signed accountability linkage.

## Implementation rule

This reverse pass does **not** mark any existing volume, work package, AIQ task, vertical slice, or edge obligation complete. It adds proof obligations and ordering constraints. Completion remains derived solely from the existing signed accountability system.

Machine mirror: `machine/ai_reverse_engineering_pass.json`
Validator: `scripts/check_ai_reverse_engineering_pass.py`
Regression tests: `skeleton/testing/test_ai_reverse_engineering_pass.py`
