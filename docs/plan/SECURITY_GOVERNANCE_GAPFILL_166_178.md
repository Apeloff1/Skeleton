# Security and Governance Gap-fill — VOL-166..VOL-178

Status: **implementation candidate; no completion, signature, scheduling, or production authority**

Machine candidate:
`machine/ai_security_governance_gapfill_candidate.json`

Exact-head validator:
`scripts/check_ai_security_governance_gapfill.py`

## Scope

This batch originally reconciled ten masterplan volumes. Current lifecycle
reconciliation shows six remain in the P3-T2 deferred queue, while four were
already scheduled by the closed P2 functional tranche. The implementation
record remains cumulative; the candidate authority now applies only to the
still-deferred subset.

The exact set is:

- VOL-166 Policy Simulation
- VOL-167 Threat Model
- VOL-169 Security Boundaries
- VOL-172 Egress Control
- VOL-173 Secret Security
- VOL-174 Key Management
- VOL-175 Tenant Isolation
- VOL-176 Privacy Engine
- VOL-177 Data Deletion
- VOL-178 Software Bill of Materials

Current P3-T2 deferred candidate set: VOL-166, VOL-173, VOL-174, VOL-176,
VOL-177, and VOL-178. Historical P2-scheduled predecessors: VOL-167, VOL-169,
VOL-172, and VOL-175. The validator proves both classifications against their
machine authorities and grants no new scheduling or completion authority.

## Reconciled existing implementation

The repository already contained substantive implementations for policy
simulation, threat coverage, outbound destination hardening, opaque secret
handles/lifecycle, key management, privacy labels, and deletion/tombstone
evidence. Their masterplan entries still pointed to broad directories or
`planned:` tests.

This batch binds those volumes to their actual modules and executable tests and
retains an explicit independent exact-head verification gap.

## New implementation depth

### VOL-167 threat change-impact triggers

The threat model now carries deterministic review triggers for authority,
identity, data, storage, network, and supply-chain boundary changes. Unknown
impact domains fail closed.

### VOL-169 explicit security boundaries

`skeleton/security/boundaries.py` models an authenticated boundary crossing.
Authorization requires the exact boundary identity plus all required scopes.
Missing authentication, scope loss, or boundary mismatch deny without retaining
effective authority.

### VOL-172 egress control

`skeleton/security/egress_control.py` layers declared host/purpose policy on
top of the existing HTTPS/DNS/rebinding defenses. Unapproved purposes fail
before DNS resolution. Mixed public/private DNS answers and unapproved public
hosts fail closed.

### VOL-175 tenant isolation

`skeleton/security/tenant_isolation.py` requires exact tenant, workspace, and
resource-prefix identity before access. Cross-tenant, cross-workspace, and
prefix-confused resources deny deterministically.

### VOL-178 SBOM

`skeleton/supply_chain/sbom.py` binds a CycloneDX-JSON contract to one exact
build artifact digest and Git revision. Components distinguish direct,
transitive, native, and container scope. Vulnerability findings must reference
components present in the same bill of materials.

## AI-tree parity

Canonical security implementations are mirrored under
`skeleton/ai/runtime/security`. SBOM is mirrored under
`skeleton/ai/runtime/extensions/supply_chain`.

The candidate validator checks byte parity and binds the exact
`AIFT-SECURITY` and `AIFT-SUPPLY-CHAIN` source-tree identities.

## Promotion boundary

No completion checkbox is promoted by this reconciliation. The candidate may not grant
implementation signatures, verification signatures, production authority, or
independent closure.

A green exact-head workflow proves only that the implementation candidate is
internally consistent on that revision. Independent closure remains a separate
authority.
