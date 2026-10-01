# ADR-0001: P2 architecture governance convergence

Status: **accepted**

Decision source: user-directed P2 implementation under the canonical masterplan.

## Context

P1 established a fail-closed production/evidence frontier. P2 begins from the 314 volumes explicitly deferred by P1 and must deepen that frozen masterplan without creating a parallel architecture authority.

The masterplan identifies concrete architecture gaps in VOL-002, VOL-051, VOL-052, VOL-053, VOL-054, VOL-055, VOL-058, and VOL-116: ownership lookup, package/import layering, manifest-reference integrity, an architecture rule registry, bounded waivers, ADR indexing, and unified fitness enforcement.

## Decision

Architecture governance in P2 uses the existing `machine/architecture.json` as topology/ownership authority and adds subordinate machine contracts for:

- architecture rule registration and executable fitness checks;
- selected high-risk Python package layering and import-direction validation;
- manifest-reference integrity and machine-to-document digest binding;
- a canonical ADR index for cross-cutting architecture changes.

These controls deepen existing volumes. They do not add a new top-level volume or replace the master build sequence, P2 execution map, signed accountability, or runtime truth.

Architecture validators remain individually executable and fail closed. Aggregate success is not maturity evidence.

## Waivers

Critical architecture-map, rule-registry, scope-freeze, and manifest-integrity controls are non-waivable. Where a specific rule allows a temporary waiver, it must be explicit, ADR-backed, independently approved, evidence-bearing, and expire within that rule's bounded TTL.

## Consequences

Architecture changes become more expensive to make silently: new checks must be registered, cross-cutting paths stay ADR-covered, selected package edges are machine-checked, and generated architecture documentation can be bound to exact machine content.

This ADR does not claim completion of P2-ARCH-01 or any masterplan volume.
