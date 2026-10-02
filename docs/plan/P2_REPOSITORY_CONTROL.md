# P2 Repository Engineering Control

Machine umbrella: `machine/repository_control.json`
Validator: `scripts/check_p2_repository_control.py`
Regression suite: `tests/test_p2_repository_control.py`

This stacked lane implements the 12 primary volumes owned by `P2-REPO-01` and remains dependent on the open P2 traceability lane.

## Control composition

The implementation composes existing repository machinery rather than replacing it:

- bounded repository indexing and Git-aware code intelligence;
- canonical architecture ownership and P2 trace impact;
- repository-machine planning and conflict-aware work graphs;
- workspace transaction leases, journals, rollback and verification;
- the 31 canonical engineering work-package profiles;
- the 42 atomic AIQ build-queue tasks;
- signed accountability records;
- the eight canonical master-build waves;
- the 57 P0/P1 edge obligations.

## Derived authorities

The lane materializes:

- a freshness/provenance-aware repository graph contract;
- inspect→plan→lease→edit→build→test→review→verify mutation governance;
- canonical maintenance ownership plus fail-closed deletion preconditions;
- an 88-item canonical backlog covering P2 tasks, edge obligations and the 24 repository-lane masterplan gaps;
- blocker-first bounded priority factors with anti-starvation;
- all 31 work packages bound to exact engineering dimensions/invariants/recovery/acceptance requirements and atomic AIQ tasks;
- high/critical historical anti-pattern lessons with explicit detectability and expiring exceptions;
- a complete wave/task construction DAG and blocked-state report;
- per-task DoD inheritance from engineering dimensions, evidence, recovery and trace-impact triggers;
- a 24-item debt ledger bound to gap, risk, owner, backlog and ADR disposition;
- roadmap items bound to both MBW and P2 dependency DAGs with revision lineage;
- signed-accountability completion rollups that refuse to average away hard blockers.

At the current source snapshot, 7 of 42 atomic AIQ tasks qualify as signed+independently verified. No package or wave qualifies as verified because package-level evidence is not yet complete, and unresolved P0 obligations keep strong completion blocked. These are derived observations, not manually assigned status.

## Safety boundaries

Generic repository deletion remains disabled. A deletion candidate needs canonical ownership, reachability evidence, retention disposition, protected-artifact handling, bounded path validation, rollback/restore evidence and a receipt.

Soft priority factors cannot outrank hard blockers. A backlog item cannot close by losing provenance. A package cannot complete from queue status alone. A roadmap item cannot expand the frozen top-level masterplan beyond VOL-420 without ADR.

This lane does not modify masterplan completion checkboxes or fabricate implementation/verification signatures.
