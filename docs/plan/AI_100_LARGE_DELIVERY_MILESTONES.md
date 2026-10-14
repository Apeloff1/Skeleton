# Skeleton AI — 100 Large Delivery Milestones

**Scope:** all 421 original masterplan volumes, grouped into 100 *large*
implementation and verification milestones, with 10 execution trains.

- Machine execution contract:
  [machine/ai_100_large_delivery_milestones.json](../../machine/ai_100_large_delivery_milestones.json)
- Validator: [scripts/check_ai_100_large_milestones.py](../../scripts/check_ai_100_large_milestones.py)
- Focused negative-test suite:
  [tests/test_ai_100_large_milestones.py](../../tests/test_ai_100_large_milestones.py)
- Canonical completion authority: `machine/ai_build_accountability.json`.
- Read-only validated navigation:
  `machine/ai_masterplan_parse_index.json`.
- AI masterplan breadth remains frozen at VOL-420; no new runtime owner,
  service or production authority is introduced by these milestones.

## 100 major milestones, not 100 completion claims

Every milestone covers **four or five full masterplan volumes** and inherits
their original implementation paths, requirements, acceptance tests, original
accountability identities, engineering expectations, and independent
verification requirements. No copied checkbox or LOC quantity can discharge
those obligations. The titles identify the first and last volume, while the
machine contract gives all exact members and their distinct acceptance tests.

The 100 existing advanced maturity levels (L001–L100) are contextual only:
they do not automatically qualify one of these delivery bundles. Each volume
must retain its own implementation and independent verification authority.

## Delivery trains

| Train | Milestones | Planning context | Closure target |
|---|---|---|---|
| MDT-01 | MDM-001–010 | Assured cognitive substrate | 10 independently verified major bundles |
| MDT-02 | MDM-011–020 | Contextual intelligence | 10 independently verified major bundles |
| MDT-03 | MDM-021–030 | Persistent knowledge intelligence | 10 independently verified major bundles |
| MDT-04 | MDM-031–040 | Deliberative intelligence | 10 independently verified major bundles |
| MDT-05 | MDM-041–050 | Governed agency | 10 independently verified major bundles |
| MDT-06 | MDM-051–060 | Organizational intelligence | 10 independently verified major bundles |
| MDT-07 | MDM-061–070 | Adaptive intelligence | 10 independently verified major bundles |
| MDT-08 | MDM-071–080 | Bounded autonomous operations | 10 independently verified major bundles |
| MDT-09 | MDM-081–090 | Scientific/metacognitive intelligence | 10 independently verified major bundles |
| MDT-10 | MDM-091–100 | Frontier governed evolution | 10 independently verified major bundles |

These are **delivery buckets**, not permission to force unrelated system
dependencies into a single production boundary. Work inside and across trains
may be parallelized subject to original work-package dependency contracts.

## Evidence-driven execution loop

1. Run `python scripts/check_ai_100_large_milestones.py` and
   `python scripts/check_ai_100_large_milestones.py --json`.
2. Choose an open bundle. Resolve the canonical VOL accountability records.
   Do not use the score as authorization to skip unresolved essential work.
3. Implement its *actual* requirements at canonical paths, including unit,
   integration, adversarial, crash recovery, resource and security tests.
4. Establish exact-head CI evidence with implementation signoff, an
   independent verifier, and replayable negative-test artifacts per volume.
5. Publish immutable source-scoped evidence through the original
   accountability/qualification process; do not edit this overlay to
   manufacture a completion state.
6. Recompute the source navigation index after any authoritative source edit.
   The validator rejects stale index and source pins until the milestone
   manifest is reviewed and regenerated from the new source identity.
7. Requalify on changes to code, policy, dependent contracts, evaluator,
   model, environment, data or implementation ownership.

### Commands

```bash
python -m unittest tests.test_ai_100_large_milestones -v
python scripts/check_ai_100_large_milestones.py
python scripts/check_ai_100_large_milestones.py --json
python scripts/check_ai_master_plan.py
python scripts/check_advanced_ai_structure.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

`--require-complete` deliberately exits unsuccessfully until all 100
milestones are independently qualified. It is a completion gate, not a
planning check. The ordinary validator may pass while 0/100 major milestones
are complete, because correctness of a backlog is not completed engineering.

## Current evidence boundary

The source parse index lists 22 fully signed volumes among 421 at the
present baseline, with 251 implementation-signed open and 148 implementation
unsigned. Those figures are **source-navigation metadata**, not newly
verified by this document. No group of four/five in the initial roadmap
contains only fully signed volumes; therefore **0/100 groups** are fully
source-signed at the initial snapshot, and **0/100** is the only defensible
independent milestone qualification count.

It is not honest to label all 100 milestones "done" merely because the
complete scope is defined. Full execution remains substantial engineering.
