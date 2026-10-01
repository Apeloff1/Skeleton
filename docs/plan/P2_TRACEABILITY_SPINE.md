# P2 Traceability Spine

Machine graph: `machine/master_traceability.json`  
Validator: `scripts/check_p2_traceability.py`  
Regression suite: `tests/test_p2_traceability.py`

This lane implements the first traceability tranche defined by the P2 execution map and remains subordinate to `machine/ai_master_plan.json`.

## Scope

The spine covers the 12 primary volumes owned by `P2-TRACE-01`:

- VOL-112 Master Traceability Matrix
- VOL-113 Capability Map
- VOL-122 Requirements Engineering
- VOL-123 Non-Functional Requirements
- VOL-124 Capability Taxonomy
- VOL-125 Capability Maturity Model
- VOL-126 Behavior Specifications
- VOL-127 State Machine Catalogue
- VOL-128 Interface Design Standard
- VOL-129 Schema Registry
- VOL-130 Compatibility Model
- VOL-131 Internal Protocols

Every machine authority carries the exact masterplan gap text it is intended to implement. The validator compares those strings back to the canonical plan and fails on narrowing or stale bindings.

## Current authority

The first materialization contains:

- 50 canonical requirement/gap IDs derived from masterplan text;
- 1,215 normalized capability IDs and mappings for all 421 masterplan volumes;
- live descriptors for the 27 planes present in the 86-edge capability-interface graph;
- maturity snapshots digest-bound to the exact masterplan and accountability Git blobs;
- 12 negative/degraded behavior scenarios;
- 5 lifecycle state sets extracted from runtime schema enums;
- interface lint rules applied across all canonical interface edges;
- 36 registered runtime schemas with conservative compatibility semantics;
- 4 internal protocol families with correlation/deadline/idempotency metadata;
- 5 independent hard NFR measurements;
- a typed master trace graph with 123 nodes and 340 edges at initial materialization.

Counts are validated from current files; the documentation count is descriptive, not completion evidence.

## Change impact

For pull requests, the dedicated workflow computes the exact base-to-head changed file list and supplies it to the trace validator. Changed paths that correspond to trace authority nodes are reverse-expanded through graph edges to affected P2 volumes and requirements.

This is impact discovery, not automatic maturity promotion. A changed authority can require revalidation even when its downstream code did not change.

## Maturity boundary

The lane intentionally does not modify volume accountability checkboxes or signatures. File presence, trace coverage, and green validators are engineering evidence; masterplan promotion still requires the canonical accountability and evidence process.
