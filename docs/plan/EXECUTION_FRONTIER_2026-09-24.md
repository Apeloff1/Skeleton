# Skeleton AI Execution Frontier — 2026-09-24

Frontier ID: **EF-2026-09-24**
Plan version: **1.6.0**
Baseline: `a2cb66b9847ff893d750aafbf6ba61d3f1a8eba0`
Prepared at: **2026-09-24T20:41:34Z**

## 1. Purpose and authority

This frontier converts the frozen long-range masterplan into an implementation-depth control surface. It does not create completion claims. The authoritative lifecycle ledger remains `machine/ai_build_accountability.json`; merged code is only candidate evidence until the required lifecycle events, exact-head acceptance evidence, independent verification, and completion digest exist.

**No task is promoted by prose.** No checkbox is checked by this file. No implementation or verification signature is fabricated.

The important state on this baseline is that implementation has advanced materially ahead of the signed ledger. Candidate evidence now reaches through Stage 3, while the ledger intentionally remains conservative.

## 2. Signed-ledger snapshot

| State | Count |
| --- | ---: |
| done | 1 |
| evidence_pending | 6 |
| in_progress | 1 |
| pending | 34 |
| **total** | **42** |

The single completed task remains `AIQ-S0-STATE-03`; `AIQ-S0-COST-02` remains the active in-progress queue task. These counts are intentionally not changed by the landed runtime work below.

## 3. Landed candidate evidence requiring reconciliation

The following **22 tasks** have concrete landed candidate evidence through Stage 3. Evidence location is not a completion claim.

| AIQ task | Ledger state | Source PR(s) | Landed candidate commit(s) | Next state if proof succeeds |
| --- | --- | --- | --- | --- |
| `AIQ-S0-COST-02` | `in_progress` | pre-frontier mainline | `ab1ecae1e1b8…` | `evidence_pending` |
| `AIQ-S0-COST-03` | `pending` | pre-frontier mainline | `029a852d6d42…` | `evidence_pending` |
| `AIQ-S0-PROV-01` | `pending` | pre-frontier mainline | `1f58a5d1c58f…` | `evidence_pending` |
| `AIQ-S0-PROV-02` | `pending` | pre-frontier mainline | `1f58a5d1c58f…` | `evidence_pending` |
| `AIQ-S0-PROV-03` | `pending` | pre-frontier mainline | `1f58a5d1c58f…` | `evidence_pending` |
| `AIQ-S1-CONV-01` | `pending` | #1980 | `d80713b71b1b…` | `evidence_pending` |
| `AIQ-S1-CONV-02` | `pending` | #1980 | `d80713b71b1b…` | `evidence_pending` |
| `AIQ-S1-MEM-01` | `pending` | #1978 | `39f4b4842413…` | `evidence_pending` |
| `AIQ-S1-MEM-02` | `pending` | #1978 | `39f4b4842413…` | `evidence_pending` |
| `AIQ-S1-MEM-03` | `pending` | #1979 | `a2cb66b9847f…` | `evidence_pending` |
| `AIQ-S1-TOOL-01` | `pending` | #1981 | `780be93964e5…` | `evidence_pending` |
| `AIQ-S1-TOOL-02` | `pending` | #1981 | `780be93964e5…` | `evidence_pending` |
| `AIQ-S1-TOOL-03` | `pending` | #1981, #1984 | `780be93964e5…`, `2df70c44e866…` | `evidence_pending` |
| `AIQ-S2-PROTO-01` | `pending` | #1986 | `f233fc044908…` | `evidence_pending` |
| `AIQ-S2-PROTO-02` | `pending` | #1986 | `f233fc044908…` | `evidence_pending` |
| `AIQ-S2-PROTO-03` | `pending` | #1986 | `f233fc044908…` | `evidence_pending` |
| `AIQ-S2-CTX-01` | `pending` | #1988 | `ded171c318d1…` | `evidence_pending` |
| `AIQ-S2-CTX-02` | `pending` | #1989 | `f274f601b945…` | `evidence_pending` |
| `AIQ-S2-CTX-03` | `pending` | #1990 | `13d6c55b566e…` | `evidence_pending` |
| `AIQ-S3-VER-01` | `pending` | #1993 | `d37e079b777e…` | `evidence_pending` |
| `AIQ-S3-VER-02` | `pending` | #1994 | `6825f5ca3a80…` | `evidence_pending` |
| `AIQ-S3-VER-03` | `pending` | #1995 | `9296af043771…` | `evidence_pending` |

Promotion chain:

```text
landed implementation
  -> exact AIQ identity
  -> task-specific focused regression evidence
  -> exact-head required CI
  -> implementation lifecycle event/signoff
  -> independent verification lifecycle event/signoff
  -> completion digest
  -> ledger promotion
```

Failed, skipped, cancelled, stale-head, or unattributable checks cannot satisfy evidence requirements.

## 4. Dependency-ordered execution waves

| Wave | Stage | Tasks | Depends on |
| --- | ---: | --- | --- |
| `EF-W0` | Stage 0 | `AIQ-S0-COST-02`, `AIQ-S0-COST-03`, `AIQ-S0-PROV-01`, `AIQ-S0-PROV-02`, `AIQ-S0-PROV-03` | — |
| `EF-W1` | Stage 1 | `AIQ-S1-CONV-01`, `AIQ-S1-CONV-02`, `AIQ-S1-MEM-01`, `AIQ-S1-MEM-02`, `AIQ-S1-MEM-03`, `AIQ-S1-TOOL-01` | `EF-W0` |
| `EF-W2` | Stage 1 | `AIQ-S1-TOOL-02`, `AIQ-S1-TOOL-03` | `EF-W1` |
| `EF-W3` | Stage 2 | `AIQ-S2-CTX-01`, `AIQ-S2-CTX-02`, `AIQ-S2-CTX-03`, `AIQ-S2-PROTO-01`, `AIQ-S2-PROTO-02`, `AIQ-S2-PROTO-03` | `EF-W2` |
| `EF-W4` | Stage 3 | `AIQ-S3-VER-01`, `AIQ-S3-VER-02`, `AIQ-S3-VER-03` | `EF-W3` |
| `EF-W5` | Stage 4 | `AIQ-S4-EXEC-01`, `AIQ-S4-EXEC-02`, `AIQ-S4-EXEC-03` | `EF-W4` |
| `EF-W6` | Stage 5 | `AIQ-S5-ENG-01`, `AIQ-S5-ENG-02`, `AIQ-S5-ENG-03`, `AIQ-S6-STREAM-01`, `AIQ-S6-STREAM-02`, `AIQ-S6-STREAM-03`, `AIQ-S7-E2E-01`, `AIQ-S7-E2E-02`, `AIQ-S7-E2E-03` | `EF-W5` |

### EF-W0 — Stage-0 evidence debt
Reconcile the five Stage-0 candidate records and independently re-check the six existing `evidence_pending` records. Lower-stage invalidation blocks dependent promotion.

### EF-W1 — conversation, memory, and canonical tool authority
This wave now includes `AIQ-S1-MEM-03`, backed by merged PR #1979. Projection stores remain derived and disposable; projection failure or rebuild loss must never become canonical memory authority.

### EF-W2 — scoped privileged tools and irreversible-action safety
Reconcile canonical tool runtime, scoped adapters, delegate-only backend registry, durable receipts, approval, idempotency, compensation, and postcondition evidence from PRs #1981 and #1984.

### EF-W3 — context/provider convergence
Reconcile provider protocol and immutable context work from PRs #1986 and #1988–#1990. Preserve provider-neutral contracts, immutable context identity, versioned instruction policy, and strict native-object/credential ownership.

### EF-W4 — verification plane
Reconcile PRs #1993–#1995. Prove scoped claims/evidence/postconditions, origin independence, deterministic grounding, bounded semantic verification, repair lineage, fail-closed high-impact finalization, and non-authority of model confidence.

### EF-W5 — bounded cognitive execution
Stage-4 work must remain bounded, durable, replayable, crash-safe, and tied to the verification/finalization contracts below it.

### EF-W6 — engine boundary, streaming, and full-stack proof
Engine, stream, and end-to-end closure remain downstream. Mocks may replace external dependencies but not erase the product boundary under proof.

## 5. Required fault families

- `duplicate-replay-idempotency-conflict`
- `restart-after-reservation-before-reconciliation`
- `crash-after-side-effect-before-receipt`
- `approval-expiry-or-argument-digest-mismatch`
- `provider-unknown-outcome`
- `dns-rebinding-redirect-private-range-egress`
- `sandbox-resource-exhaustion`
- `stale-lease-aba-owner-fencing`
- `multi-tenant-pressure-fairness`
- `event-duplication-reordering-gap`
- `reconnect-during-terminal-commit`
- `stale-context-or-policy-digest`
- `tombstone-projection-rebuild`
- `verifier-evidence-head-mismatch`

## 6. Promotion stop conditions

Stop promotion and repair first when:
- exact-head CI is absent or not attributable to the candidate head;
- a required gate is skipped, cancelled, failed, stale, or only a mirrored pending status;
- implementation evidence does not bind to the exact AIQ record;
- a lower-stage contract changed after dependent evidence was recorded;
- implementation or independent-verification signoff is missing;
- a completion digest cannot be reproduced;
- a candidate depends on obsolete stacked ancestry instead of landed mainline code.

## 7. Current next construction direction

With candidate implementation landed through Stage 3, the next net-new construction frontier is Stage 4 (`AIQ-S4-EXEC-01..03`) after accountability reconciliation and repair of any invalidated lower-stage evidence.

```text
EF-W0 ledger reconciliation
  -> EF-W1/2/3/4 evidence reconciliation
  -> EF-W5 bounded cognitive execution
  -> EF-W6 engine/stream/full-stack closure
```

Plan-preparation status: **prepared, not implementation-signed, not independently verified**.
