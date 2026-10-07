# Canonical Contract Conformance

<!-- machine-git-blob: machine/contract_conformance.json@5302df35e2c363308018e466d9459130d00f2c5f -->

Machine authority: `machine/contract_conformance.json`

This control implements VOL-003's two explicit P2 gaps:

- a complete producer/consumer plane inventory for every record in `machine/ai_runtime_schemas.json`;
- shared fail-closed serialization/schema conformance vectors.

Producer ownership is always the schema record's `owner_plane`. Consumer planes derive mechanically from incoming capability-interface edges. Three records whose owner planes currently have no incoming graph edges—`ResourceBudget`, `StreamEvent`, and `AdmissionDecision`—carry explicit reviewed consumer overrides and rationales rather than disappearing from the inventory.

The shared corpus currently exercises duplicate JSON keys, NaN/Infinity, Unicode round-trip, missing required fields, explicit nullability, and unknown enums. These vectors are architecture conformance evidence only and do not promote masterplan maturity.
