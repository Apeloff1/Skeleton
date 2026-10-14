# October 2026 Engineering Standards — VOL-221..VOL-234

Status: **implementation candidate; no completion, verification signature, release authority, routing authority, SOTA authority, or production authority**

Candidate:
`machine/ai_oct2026_engineering_standards_candidate.json`

Exact-head validator:
`scripts/check_ai_oct2026_engineering_standards.py`

## Scope

This pass implements fourteen deferred volumes:

- VOL-221 Model Card System
- VOL-222 Dataset Card System
- VOL-223 Tool Card System
- VOL-224 Agent Card System
- VOL-225 Component Health Scorecard
- VOL-226 Dependency Health
- VOL-227 Vendor / Provider Risk
- VOL-228 Provider Failover
- VOL-229 Offline Mode
- VOL-230 Air-Gapped Profile
- VOL-231 Edge Deployment
- VOL-232 Enterprise Deployment
- VOL-233 Identity Federation
- VOL-234 Administration Plane

All fourteen remain explicitly queued and unscheduled.

## October 2026 engineering baseline

The batch treats the following as mandatory engineering properties rather than
optional documentation conventions.

### Evidence is content-addressed

Cards, health reports, provider risk, deployment profiles, federation sessions,
and review artifacts bind exact SHA-256 evidence. The tranche-level review binds
all fourteen surfaces to one exact Git revision.

### Descriptive artifacts never become authority

Model, dataset, tool, and agent cards cannot grant promotion authority.
Provider-risk and failover receipts cannot grant routing authority. Deployment
profiles cannot grant production authority.

### Fail closed at authority boundaries

Privileged tools require explicit approval. Administration requires declared
capability scope plus approval or an explicit break-glass receipt. Break-glass
cannot silently reuse the normal approval path.

Federated identities bind issuer, external subject, local principal, tenant,
scope, session window, and revocation epoch. A mismatch, expired session,
revocation change, or scope escalation produces no effective authority.

### Provider resilience preserves capability

Provider failover selects only healthy, lower-risk providers in the same
capability class that satisfy the required feature set and context capacity.
Failover cannot silently expand capability.

Provider risk records availability, security, privacy, regulatory, and lock-in
dimensions and derives the failover requirement from evidence rather than a
caller-controlled flag.

### Offline and air-gap are explicit modes

Offline capability declarations cannot require network access. Offline profiles
require local model/storage evidence when their capabilities depend on them and
forbid provider calls.

Air-gapped installations bind package artifact, SBOM, provenance, signature,
trusted-root, and removable-media scan evidence. Network and online updates
remain disabled by contract.

### Deployment topology is machine-checkable

Edge profiles bind memory, storage, accelerator, context capacity, allowed
model classes, and router policy.

Enterprise profiles require multiple zones, redundant replicas, tenant
isolation, auditing, security-boundary evidence, acceptance evidence, and the
administration-plane identity.

### Health is evidence, not a dashboard opinion

Component health is deterministically weighted from evidence-bound dimensions.
Dependency health is bound to the SBOM and requires backlog identity for each
finding. High/critical findings prevent a healthy report.

## AI-tree ownership

A new canonical native owner, `AIFT-NATIVE-GOVERNANCE-ROOT`, governs the
standards plane under `skeleton/ai/governance`.

Provider risk/failover/offline remain under the provider native owner. Edge and
enterprise deployment profiles remain under the runtime native owner. Air-gap
and identity-federation controls extend the exact `AIFT-SECURITY` mirror.

## Verification boundary

The shared engineering-standards review requires a verifier identity distinct
from the producer. All completion boxes remain false. Green exact-head CI means
implementation consistency only; independent verification/signing remains a
separate authority.
