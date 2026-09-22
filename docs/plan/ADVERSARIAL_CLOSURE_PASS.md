# Masterplan Adversarial Closure Pass

Pass version: **1.0.0**
Created: **2026-09-22T11:48:00Z**
Scope: **depth-only; Volume 420 breadth freeze preserved**
Machine contract: [`machine/ai_adversarial_closure.json`](../../machine/ai_adversarial_closure.json)

## Purpose

The masterplan already has wide architecture coverage, edge-case ownership, signed accountability, build waves, and a systems-engineering closure chain. The remaining adversarial weakness is **interaction risk**: a work package can satisfy requirement, interface, failure, recovery, budget, compatibility, observability, and evidence dimensions independently while still failing when those conditions combine.

This pass closes that loophole without adding a new top-level architecture domain.

The law is:

```text
single-dimension proof
  + cross-condition interaction proof
  + compound-fault proof
  + replayable recovery
  + independent artifact-bound evidence
  = eligible for strong maturity promotion
```

A green aggregate workflow, a passing happy path, or a list of planned tests cannot substitute for this chain.

## Adversarial findings

The review found 24 proof gaps that were representable inside the frozen plan but not strongly enough bound to promotion. They are now machine-enforced closure axes.

| ID | Closure axis | WP coverage | Hard stop |
| --- | --- | ---: | --- |
| AC-01 | Bootstrap and root trust | 7 | Promotion stops if initial trust, re-root, or dependency-reduced bootstrap is implicit. |
| AC-02 | Quiescence, shutdown, and restart | 15 | No hardened claim while shutdown can strand authority or repeat a side effect. |
| AC-03 | Hard resource exhaustion | 31 | A package cannot be production-ready if exhaustion becomes corruption, deadlock, or unbounded retry. |
| AC-04 | Dependency degradation and capability contraction | 21 | Fallback may not silently increase privilege, data exposure, or irreversible behavior. |
| AC-05 | Unknown external outcome | 11 | Unknown side-effect outcome must enter reconciliation, not blind retry. |
| AC-06 | Reconciliation, duplicates, and orphans | 23 | Every durable projection/effect path must have a bounded reconciliation story. |
| AC-07 | Mixed-version migration and rollback | 31 | No strong promotion without a proven mixed-version window or an explicit stop-the-world contract. |
| AC-08 | Restore versus deletion and external reality | 23 | Restore is incomplete until deletion, identity, leases, and external effects are reconciled. |
| AC-09 | Time, expiry, and lease semantics | 29 | Time-dependent authorization or ownership must not rely on unqualified wall-clock assumptions. |
| AC-10 | Identity, credential, and key continuity | 17 | Stale or restored credentials may not regain authority without revalidation. |
| AC-11 | Semantic drift without version change | 16 | Cached compatibility/eval claims expire when semantic canaries detect material drift. |
| AC-12 | Canonicalization, TOCTOU, and exact-resource execution | 11 | Authorization must bind the exact normalized resource or immutable identity actually executed. |
| AC-13 | Hostile input and parser/resource bombs | 15 | Input acceptance must be bounded by size, depth, expansion, and compute limits. |
| AC-14 | Evidence integrity and verifier independence | 31 | Verified/hardened/production claims require artifact-bound, retained, independently checkable evidence. |
| AC-15 | Economic denial of service and budget overshoot | 18 | Budget overshoot must degrade or stop predictably before shared-service starvation. |
| AC-16 | Observability failure and telemetry pressure | 31 | Core correctness may not depend on telemetry availability; critical recovery evidence must remain reconstructable. |
| AC-17 | Cross-tenant and cross-workspace isolation | 23 | Tenant/workspace identity must be part of every authoritative lookup, cache key, receipt, and replay boundary. |
| AC-18 | Data lifecycle, rebuild, and compaction | 22 | Derived state must be rebuildable from authoritative inputs without resurrecting forbidden or stale data. |
| AC-19 | Human override, break-glass, and operator error | 15 | Human override is auditable, time-bounded, least-authority, and cannot erase evidence. |
| AC-20 | Plan, machine contract, and implementation drift | 31 | Promotion stops on unresolved target/current drift or machine/human contract disagreement. |
| AC-21 | Recovery dependency cycles and dependency-reduced safe mode | 14 | Critical recovery paths require an acyclic bootstrap or a documented dependency-reduced safe mode. |
| AC-22 | Reproducibility, hermeticity, and environment drift | 18 | High-impact evidence must bind environment identity and survive reproducible replay. |
| AC-23 | Long-horizon entropy and aging | 31 | No production claim based only on short-lived happy-path runs where aging changes semantics. |
| AC-24 | Compound-fault closure | 31 | Applicable critical compound campaigns must pass or carry explicit signed risk acceptance before production promotion. |

## Cross-condition laws

1. **Bootstrap is part of architecture.** Empty-machine first start, trust-root establishment, re-root, and dependency-reduced safe mode must be testable.
2. **Shutdown is a state transition, not process death.** In-flight authority and side effects must drain, fence, reconcile, or resume deterministically.
3. **Hard exhaustion is different from high load.** ENOSPC, OOM, FD exhaustion, quota exhaustion, provider credit/rate exhaustion, and context exhaustion require explicit behavior.
4. **Fallback contracts authority, privacy, capability, and cost.** A degraded dependency may never justify silent privilege or data-boundary widening.
5. **Unknown outcome is a first-class state.** Timeout after a possible external commit routes to reconciliation, not blind retry.
6. **Restore is not complete when bytes load.** Tombstones, revoked credentials, leases, external effects, derived indexes, and newer remote reality must be reconciled.
7. **Time is an input.** Monotonic deadlines, wall-clock timestamps, TTLs, lease epochs, clock skew, suspend/resume, and expiry must not be conflated.
8. **Identity must survive lifecycle change without preserving stale power.** Reinstall, restore, rotation, revocation, delegation, and historical verification are separate concerns.
9. **Semantic version identifiers are not proof of semantic stability.** Provider/model/tool drift requires active canaries and evidence invalidation.
10. **Authorize the exact resource that executes.** Canonicalization, redirects, symlinks, DNS, case, Unicode, archives, and TOCTOU are pre-execution security concerns.
11. **Evidence is an attack surface.** Failed runs are retained; verifier independence is measurable; evidence binds code, config, environment, artifact, and fault manifest.
12. **Recovery must work when normal infrastructure is broken.** Critical recovery paths cannot depend cyclically on the failed scheduler, queue, identity store, telemetry, or model plane.
13. **Long-horizon aging is testable.** Certificate expiry, TTLs, counters, cache staleness, storage growth, memory leaks, model retirement, and provider deprecation must be accelerated or soaked.
14. **Compound faults are mandatory on consequential paths.** Single-axis chaos is insufficient for irreversible effects, authority, promotion, rollback, and trust roots.

## Canonical compound-fault campaigns

These campaigns are not exhaustive. They are the minimum permanent set required to prevent the most dangerous interaction gaps from disappearing behind independent green checks.

| ID | Campaign | Primary WPs | Oracle |
| --- | --- | --- | --- |
| CCF-01 | Effect committed, receipt lost, retry races | WP-W04, WP-W13, WP-W19, WP-W22, WP-W30 | Exactly one external effect; eventual authoritative receipt; no blind retry. |
| CCF-02 | Point-in-time restore with rotated keys and newer object state | WP-W03, WP-W20, WP-W25, WP-W30 | Restored state cannot revive revoked authority; external/object divergence is reconciled. |
| CCF-03 | Partition plus lease expiry plus clock skew plus stale worker | WP-W03, WP-W04, WP-W15, WP-W16, WP-W29 | Only current fenced owner may commit; stale worker writes are rejected. |
| CCF-04 | Provider semantic drift during privacy-sensitive fallback | WP-W05, WP-W06, WP-W10, WP-W20, WP-W30 | Fallback narrows or preserves privacy/authority; drift invalidates stale compatibility evidence. |
| CCF-05 | Disk full plus telemetry backpressure plus cancellation | WP-W02, WP-W03, WP-W19, WP-W21, WP-W22, WP-W30 | Control path remains bounded; terminal state is reconstructable; no corruption. |
| CCF-06 | Cross-tenant cache collision under eviction and replay | WP-W07, WP-W08, WP-W10, WP-W22, WP-W29 | No cross-tenant data appears; replay retains tenant identity. |
| CCF-07 | Mid-migration rollback with old reader and new writer | WP-W01, WP-W03, WP-W04, WP-W25, WP-W30 | Compatibility contract either preserves correctness or blocks the unsafe mixed state. |
| CCF-08 | Trust-root compromise during repair/bootstrap | WP-W00, WP-W20, WP-W24, WP-W25, WP-W30 | Re-root is possible without trusting compromised normal-plane state; history remains verifiable. |
| CCF-09 | Swarm fan-out plus underestimated cost plus provider throttling | WP-W06, WP-W11, WP-W12, WP-W15, WP-W16, WP-W29 | Fan-out contracts, budgets contract, and service remains fair under throttling. |
| CCF-10 | Contaminated benchmark plus correlated verifier plus promotion pressure | WP-W17, WP-W18, WP-W26, WP-W27, WP-W28 | Candidate cannot self-validate or promote; contamination/correlation is surfaced. |
| CCF-11 | Interrupted installer/update with partial config and old binary | WP-W24, WP-W25, WP-W30 | Restart reaches old-known-good or new-complete state; never an undocumented hybrid. |
| CCF-12 | Deletion request followed by backup restore and stale derived indexes | WP-W03, WP-W07, WP-W08, WP-W09, WP-W20, WP-W30 | Deletion/tombstones dominate restore and rebuild; derived state cannot resurrect deleted data. |

## Promotion gates

- **ADV-E0 Applicability:** every axis is explicitly applicable or not-applicable with rationale.
- **ADV-E1 Single-axis evidence:** high-impact applicable axes have executable artifact-bound evidence.
- **ADV-E2 Pairwise interaction:** consequential authority/state/side-effect/recovery paths have pairwise fault coverage.
- **ADV-E3 Compound campaigns:** applicable CCF campaigns pass their oracle or carry explicit signed risk acceptance.
- **ADV-E4 Recovery replay:** recovery/rollback/restore can be replayed from manifests without undocumented operator state.
- **ADV-E5 Independent closure:** high-impact evidence has independent verification and signed accountability bound to digests.

Gates are cumulative. Later evidence never erases an earlier failure.

## Evidence bundle

A closure bundle records at minimum:

```text
git_sha
artifact_digest
config_digest
environment_digest
fault_manifest_digest
work_package_refs
axis_refs
campaign_refs
result
raw_evidence_refs
started_at_utc
completed_at_utc
verifier_identity
signoff_ref
```

The fault manifest must name the injected conditions, timing/order, expected oracle, seed or replay identity when applicable, and any unavailable fault mechanism. A run that cannot be reproduced remains evidence of an observation, not proof of a general guarantee.

## Forbidden shortcuts

The following do not close an adversarial obligation:

- aggregate green CI hiding a failed critical obligation;
- planned tests treated as passing evidence;
- generator output treated as independent verification;
- fallback without authority/privacy/cost comparison;
- restore declared complete before external-effect and tombstone reconciliation;
- retry after unknown outcome without reconciliation;
- `N/A` without rationale;
- short happy-path runs used to waive aging risk;
- undocumented operator knowledge as a recovery dependency;
- machine/prose/implementation drift without a tracked gap;
- single-fault testing used to waive applicable compound campaigns;
- file presence or LOC used as proof of verified behavior.

## Work-package integration

The machine contract maps every `WP-W00` through `WP-W30` to at least six closure axes. Builders do **not** create parallel work-package identities. They attach the relevant axis/campaign references to the existing build packet, tests, evidence, and accountability ledger.

A work package may implement before all adversarial obligations are closed. It may not claim `verified`, `hardened`, or `production` while an applicable high-impact obligation is unresolved.

## Change-impact triggers

Re-run adversarial applicability whenever a change affects:

- authoritative state, lifecycle, retry, idempotency, or reconciliation;
- identity, policy, trust roots, credentials, delegation, or tenant/workspace scope;
- persistent schema, storage, cache/index derivation, deletion, migration, restore, or compaction;
- provider/model/tool behavior, fallback, routing, budget, or data residency;
- installer/update/bootstrap/recovery dependencies;
- telemetry/evidence/signing/provenance;
- queueing, scheduling, leases/fencing, distributed placement, or capacity reserves;
- any external side effect or irreversible promotion path.

## Completion rule

This pass is complete as a **planning artifact** when its machine contract, human contract, validator, tests, masterplan references, and CI wiring are present and green.

It is complete as **production evidence** only when the applicable axes and compound campaigns for a capability have real artifact-bound evidence and required independent sign-off.

No signatures are fabricated by this planning pass.
