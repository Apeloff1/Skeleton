# P2 Execution Map

Map version: **0.3.0**

Machine authority: [`machine/ai_p2_execution_map.json`](../../machine/ai_p2_execution_map.json)
Task backlog: [`machine/ai_p2_task_backlog.json`](../../machine/ai_p2_task_backlog.json)
Validator: [`scripts/check_p2_execution_map.py`](../../scripts/check_p2_execution_map.py)

## Boundary

P2 begins from `8a0de9a4ee28f92ce01f59862cadc55a2f420b11`, where the governed P1 risk/evidence frontier records **513 resolved / 0 blocking / 0 unclassified** obligations.

P1 intentionally scoped its trustworthy-production frontier to 107 primary volumes and explicitly deferred **314** masterplan volumes. P2 takes those 314 deferred references as its source scope. It does **not** reopen the P1 frontier, reinterpret P1 supporting references as P2 ownership, or weaken P1 fail-closed/evidence guarantees.

The baseline commit currently exposes no commit statuses or workflow runs through the connected GitHub surface. That absence is not treated as proof. P2 therefore establishes fresh exact-head validation for its own control plane.

## First tranche

The first tranche schedules **42** of the 314 P2 source volumes and leaves **272** explicitly queued.

The tranche is deliberately control-heavy: architecture and contract convergence first, then requirements/schema/traceability, then autonomous repository engineering, quality/final assembly, evidence-bound documentation, and finally profiling-gated native/JVM acceleration.

This ordering is designed to prevent a new breadth explosion before P2 has trustworthy ownership, change-impact, dependency, evidence, and progress-control primitives.

## Lanes

| Lane | Name | Depends on | First task |
| --- | --- | --- | --- |
| P2-L0 | Scope & promotion authority | — | P2-CTRL-01 |
| P2-L1 | Architecture & contract convergence | P2-L0 | P2-ARCH-01 |
| P2-L2 | Requirements, schemas & traceability | P2-L1 | P2-TRACE-01 |
| P2-L3 | Repository intelligence & engineering control | P2-L1, P2-L2 | P2-REPO-01 |
| P2-L4 | Formal quality & assembly qualification | P2-L2 | P2-QUAL-01 |
| P2-L5 | Evidence-bound documentation | P2-L2 | P2-DOC-01 |
| P2-L6 | Profile-gated acceleration | P2-L4 | P2-NATIVE-01 |

## Masterplan inheritance

P2 is subordinate to the canonical masterplan rather than a parallel planning system. The machine map pins masterplan version/status, the Volume 420 breadth freeze, the canonical master-build sequence, and the masterplan maturity/anti-shortcut rules.

For every scheduled primary volume, the P2 backlog now inherits the masterplan's exact title, depth-pass identity, accountability ID, current implementation state, signing requirement, contracts, risks, and gaps. The validator compares those inherited records to `machine/ai_master_plan.json` on every run. A task-local objective may add constraints, but it cannot shorten the masterplan's risk/gap/contract obligations.

P2 task dependencies supplement the eight canonical `MBW-00..07` construction waves; they do not replace build-wave gates, AIQ dependencies, vertical-slice evidence, maturity rules, or signed accountability.

## Fail-closed invariants

1. The P2 source set must equal the P1 `deferred_volume_refs` set exactly.
2. Scheduled and queued sets must be disjoint and cover the complete P2 source set.
3. A scheduled primary volume has exactly one task owner.
4. Task and lane dependency graphs must be acyclic and reference known nodes.
5. No task may claim a primary volume outside the P2 source scope.
6. No completion checkbox may be asserted by this foundation map.
7. P2 may deepen P1 owners but may not weaken P1 authority, evidence, recovery, or exact-head rules.

## Current implementation order

`P2-CTRL-01`, `P2-ARCH-01`, and `P2-TRACE-01` have landed implementation evidence but remain **unpromoted**: no completion checkbox, maturity promotion, or sign-off is inferred from landing.

With traceability landed, the dependency-ready implementation lanes are active in parallel:

- `P2-REPO-01` — repository engineering/control plane (#2318, followed by stacked #2321).
- `P2-QUAL-01` — formal quality and final-assembly qualification (#2320).
- `P2-DOC-01` — evidence-bound generated documentation (#2322).

`P2-NATIVE-01` remains blocked on `P2-QUAL-01`; its staged implementation (#2323) may be hardened, but it cannot be promoted ahead of the quality lane.

The remaining 272 volumes stay visible in the machine map. They are queued, not discarded.
