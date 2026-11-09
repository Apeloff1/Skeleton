# P2 Traceability Spine

Canonical master trace: `machine/master_traceability.json` + `machine/traceability/*.json`
Canonical validator: `scripts/check_traceability_spine.py`
Focused projection validator: `scripts/check_p2_traceability.py`

P2-TRACE-01 remains subordinate to `machine/ai_master_plan.json`. It covers exactly VOL-112, VOL-113, and VOL-122 through VOL-131 and does not promote any of those volumes.

## Canonical authority

The merged deep trace spine is the requirements-to-runtime authority. It currently derives all 421 frozen masterplan volumes into:

- 963 stable requirement identities;
- 9,115 trace nodes;
- 25,119 typed edges;
- 11 depth-pass shards;
- explicit test/evaluation/evidence lineage;
- 37 engineering-derived NFR identities;
- full capability taxonomy mappings;
- schema/interface compatibility and state-machine registries;
- a canonical internal protocol envelope;
- evidence-digest maturity invalidation.

The canonical graph remains fail-closed on dangling references, missing test lineage, stale derived registries, and unmapped implementation impact.

## Focused P2 projections

Three smaller machine files are deliberately projections, not competing authorities:

- `machine/capability_registry.json` projects runtime plane presence from `machine/capability_interfaces.json`;
- `machine/capability_maturity.json` observes only the 12 P2-TRACE volumes and cross-checks `machine/maturity_registry.json`;
- `machine/internal_protocols.json` groups four runtime protocol/schema families while `machine/protocol_registry.json` remains canonical envelope/migration authority.

The focused validator runs the canonical deep validators first. A focused projection can therefore never turn a broken master trace green.

## Independent CI

Two independently named workflows validate this lane:

- **P2 Master Traceability Spine** validates the sharded 421-volume graph, NFRs, change impact, maturity invalidation, and canonical protocol envelope.
- **P2 Traceability Focused Contract** validates the deep spine again, then the three focused P2 projections and the exact P2-TRACE-01 task boundary.

Their concurrency groups are intentionally different so neither workflow can cancel the other.

## Maturity boundary

P2-TRACE-01 remains `in_progress`. Its completion checkbox is false, implementation/verification signatures are false, and no green workflow is interpreted as maturity promotion. Evidence and implementation can land before the canonical accountability process promotes a masterplan volume.
