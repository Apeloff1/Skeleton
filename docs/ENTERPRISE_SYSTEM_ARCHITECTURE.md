# Skeleton Enterprise System Architecture — October 2026

**Status:** architecture plan complete candidate  
**Production-ready claim:** **NO** — promotion requires runtime evidence  
**Machine contract:** `machine/enterprise_system_architecture.json`  
**Validator:** `python scripts/check_enterprise_system_architecture.py`  
**Independent verifier:** `python scripts/verify_enterprise_system_architecture.py <receipt>`  
**Existing architecture:** `machine/architecture.json` / `docs/ARCHITECTURE_MAP.md`  
**AI construction:** `machine/ai_app_construction.json` / `docs/AI_APP_CONSTRUCTION_MANUAL.md`

## 1. Purpose

Skeleton already has strong component architecture: canonical roots, 27 AI capability
planes, explicit interface edges, state-authority topology, durable operations,
provider/tool/memory/retrieval boundaries, release controls, and a five-service
application manifest.

This document defines the layer that makes those parts one **working enterprise
system**.

The enterprise architecture is not a second application architecture. It is the
system-of-systems contract that answers the production questions that component
maps alone cannot answer:

- What must be highly available?
- Which state is authoritative, derived, scratch, or recoverable?
- How are tenants isolated?
- How do services authenticate to each other?
- What happens when providers, databases, networks, workers, deployments, or
  operators fail?
- What are the SLOs, RPOs, and RTOs?
- How does overload behave?
- Which telemetry pages a human?
- How are releases promoted and rolled back?
- Which runbooks and disaster drills are mandatory?
- What exact evidence allows the repository to claim "enterprise production
  ready"?

The governing rule is:

> **Documentation can complete the architecture plan. Only runtime evidence can
> complete the enterprise system.**

## 2. Enterprise system boundary

The deployable product remains the runtime cell declared by
`skeleton/app/manifest.json`:

```text
Internet / client
      |
      v
+------------------+
| frontend         |  edge/product tier
+------------------+
      |       \
      |        \
      v         v
+----------+  +----------+
| backend  |  | skeleton |  application + AI engine tiers
+----------+  +----------+
     \          /
      \        /
       v      v
       +-------+
       | mongo |             canonical durable authority
       +-------+

       +--------+
       | chroma |             optional derived retrieval projection
       +--------+
```

The five service identities are fixed by the runtime manifest:

1. `frontend`
2. `backend`
3. `skeleton`
4. `mongo`
5. optional `chroma`

A production deployment may replace Docker Compose with Kubernetes, Nomad,
ECS, a managed platform, or another scheduler. That does **not** change the
system contract. Orchestration technology is replaceable; authority, security,
state, recovery, admission, and evidence semantics are not.

## 3. Production runtime cell

### 3.1 Edge/product tier

`frontend` is the public human-interface root.

Production requirements:

- at least two serving replicas or equivalent failure-domain redundancy;
- TLS termination at trusted ingress;
- bounded request sizes and connection limits;
- no direct database exposure;
- no provider credentials;
- no canonical conversation authority;
- reconnectable product state reconstructed from server authority;
- graceful degraded UX when engine-dependent features are unavailable.

The frontend owns presentation. It never becomes a recovery store.

### 3.2 Application-control tier

`backend` owns product API policy, conversation-facing workflows, operator
control surfaces, and composition of product-facing engine work.

Production requirements:

- horizontally scalable request-serving instances;
- no correctness dependency on process-local mutable state;
- authenticated and authorized service calls to the engine;
- idempotency for retryable mutations;
- explicit overload/backpressure behavior;
- canonical conversation writes through durable authority;
- bounded shutdown drain;
- readiness that reflects required dependency health.

### 3.3 AI-engine tier

`skeleton` owns AI execution, model/provider boundaries, orchestration,
context, tools, memory, retrieval, verification, governance integration,
durable operation semantics, and engine API composition.

Production requirements:

- horizontally scalable workers/serving instances;
- execution ownership fencing for mutable durable operation progression;
- provider and tool side effects bound to durable identities and receipts;
- no authority inferred from model text;
- no credentials exposed to product routes or model context;
- capacity/admission control before expensive execution;
- safe resume after process restart;
- circuit breaking and compliant provider failover;
- readiness that never claims unavailable capabilities as healthy.

### 3.4 Canonical data tier

MongoDB is the primary canonical durable store in the current runtime
architecture.

A production profile requires:

- replicated/quorum-capable topology;
- transaction capability required by active write contracts;
- encrypted storage;
- backup + point-in-time recovery where supported;
- no public network ingress;
- authentication and least-privilege database identities;
- capacity headroom and storage alerts;
- tested restore semantics;
- application acknowledgement only after the canonical durability contract is
  satisfied.

A single-node developer Mongo is **not** a production topology.

### 3.5 Derived retrieval tier

Chroma is optional and non-canonical.

The contract is:

- it may accelerate or enrich retrieval;
- it never becomes the only copy of user/governance/conversation authority;
- ACL/tenant filtering occurs before unsafe ranking exposure;
- stale or unavailable projection must degrade explicitly;
- projection can be rebuilt from canonical state and registered source data;
- recovery of derived retrieval never blocks restoring canonical authority
  first.

## 4. Enterprise domain model

The 27 construction planes are grouped into enterprise operational domains.

| Enterprise domain | Capability planes | Enterprise responsibility |
| --- | --- | --- |
| Product edge | product-experience, streaming-realtime | Human ingress, reconnect UX, product projection |
| Application control | application-api, operator-control | Product policy and authenticated workflows |
| AI execution | model-provider, model-routing, prompt-context, orchestration, reasoning-verification, tool-runtime | Bounded governed AI execution |
| Canonical state | data-persistence, jobs-durability, memory, artifact-files | Durable authority and recovery metadata |
| Retrieval/knowledge | retrieval | Authorized evidence and rebuildable search projection |
| Identity/security | identity, configuration-secrets, security-safety, governance | Auth, secret custody, data/security policy |
| Reliability/capacity | resilience, cost-capacity | Backpressure, budgets, circuit breaking, degradation |
| Observability/evaluation | observability, evaluation | SLI, evidence, release qualification |
| Learning/feedback | feedback-learning | Governed improvement proposals |
| Delivery/release | deployment-release | Build provenance, canary, promotion, rollback |
| Foundation | foundation, engine-api | Kernel primitives and engine API composition |

A domain grouping does not transfer ownership. Canonical plane owners remain the
source of truth.

## 5. Authority law

The system must be designed so that every important fact has exactly one
authoritative owner.

### 5.1 Canonical state

Canonical state includes:

- conversation threads/messages;
- durable operation journals and terminal result identity;
- governance and approval receipts;
- tool execution receipts;
- canonical memory records;
- artifact lifecycle metadata and canonical payload references;
- release evidence and production promotion receipts.

### 5.2 Derived state

Derived state includes:

- vector indexes;
- caches;
- search materializations;
- precomputed summaries;
- UI caches;
- telemetry aggregates.

Derived state may be stale, missing, or rebuilt. It must not silently become
authoritative during an outage.

### 5.3 Scratch state

Scratch state includes:

- temporary uploads;
- provider request staging;
- sandbox workspaces;
- temporary build artifacts;
- transient model/tool intermediate output.

Scratch state receives hard lifetime and size bounds.

## 6. Tenant architecture

The default enterprise topology is a shared platform with mandatory logical
tenant isolation.

The minimum binding for protected work is:

```text
tenant_id
  + principal_id
  + operation_id
  + capability/resource
  + data class
  + action risk
  + approval state (when required)
```

### 6.1 Authorization model

Use layered authorization:

- RBAC for coarse organizational roles;
- resource/tenant attributes for isolation;
- capability policy for what can be attempted;
- data-class policy for what may cross a boundary;
- action-risk policy for approvals and stronger authentication;
- request-bound grants for consequential side effects.

Network position is never authorization.

### 6.2 Privileged access

Production administration requires:

- separate human admin identity;
- strong authentication;
- just-in-time elevation;
- bounded expiry;
- named reason/ticket;
- immutable audit;
- explicit break-glass path;
- post-event review.

Long-lived omnipotent administrator tokens are not part of the target
architecture.

## 6.3 Enterprise identity federation

Human enterprise authentication should federate through OIDC by default. SAML
can be supported through an identity broker when a customer requires it.

Directory synchronization such as SCIM may provision users and groups, but the
external directory does not become Skeleton's runtime authorization authority.
Skeleton still decides resource, tenant, capability, data-class and action
permissions.

Privileged production sessions require strong authentication, bounded session
lifetime, revocation, and re-authentication for high-impact actions.

## 6.4 Consistency and transaction model

Canonical writes use the strongest consistency promised by the owning
repository. A successful acknowledgement is emitted only after the declared
durability point.

Concurrent operation progression uses monotonic state, idempotency, leases,
fencing and compare-and-swap where appropriate.

Derived projections are eventually consistent and freshness is explicit.

When one ACID transaction cannot span two authority owners, cross-service
mutation uses saga/outbox/receipt semantics. An ambiguous side effect must be
reconciled before retry.

Strong/current reads are required for authorization, governance, irreversible
side effects, and terminal completion claims. Bounded-stale reads are permitted
only where policy says they are safe.

Audit timestamps use UTC. Local timeout/deadline correctness uses monotonic
clocks and must not depend on wall-clock synchronization.

## 6.5 Regional and residency strategy

The first enterprise production target is one active region distributed across
multiple failure domains, with encrypted recovery copies in a second region.

The recovery region may be warm-standby or restore-driven as long as the
declared region-loss RPO/RTO is met.

Active-active multi-region canonical writes are **not** assumed to be safe.
They are forbidden until conflict handling, tenant routing, global idempotency,
provider residency, and failover semantics are independently proven.

Tenant/jurisdiction residency policy constrains:

- canonical storage;
- backups;
- retrieval/index placement;
- model-provider egress;
- tool/integration egress.

## 6.6 Configuration and feature flags

Non-secret configuration is versioned and schema-validated.

Production secrets are references to external secret custody, not values
committed to repository files.

Feature flags require:

- owner;
- purpose;
- safe default;
- rollback behavior;
- expiry or review date.

Configuration capable of changing production behavior receives the same
provenance and rollout discipline as code.

## 6.7 External dependency registration

Every production external dependency must be registered with:

- owner;
- purpose;
- authentication;
- data classes;
- regions/residency;
- timeout;
- retry safety;
- concurrency/rate limits;
- health/SLO signal;
- fallback/degraded behavior;
- audit/provenance;
- exit/replacement plan.

An undeclared external dependency is production-ineligible.

## 6.8 Architecture exception policy

Exceptions are temporary risk instruments, not alternate architecture.

Every exception needs:

- unique ID;
- owner;
- scope;
- risk;
- compensating controls;
- approval;
- created and expiry timestamps;
- remediation plan.

Exceptions cannot waive tenant isolation, production secret protection,
acknowledged canonical-write durability, privileged mutation audit, or the rule
that model output is not authorization.

Expired exceptions block architecture/release acceptance until removed or
renewed with new evidence.

## 6.9 API and contract governance

Public APIs are versioned, bounded, documented and compatibility-tested.

Internal APIs are schema-governed with explicit ownership and failure behavior.

Breaking changes use versioning or expand/migrate/contract rollout. Silent
wire-shape breakage is prohibited.

Externally retried mutations require idempotency whenever duplicate effects are
possible.

Errors use stable machine-readable classes, sanitized public detail, and an
internal correlation identity.

## 7. Service-to-service trust

The target production model is short-lived workload identity.

Protected service mutations should converge on:

```text
authenticated workload
      |
      v
mutually authenticated transport
      |
      v
delegated request authority
      |
      v
target service authorization
      |
      v
durable mutation + receipt
```

Existing signed delegated authority remains valid during migration. The
enterprise end-state removes reliance on static shared service credentials for
new production trust.

## 8. Security architecture

Security is fail-closed at protected boundaries.

Mandatory control families:

- identity/session assurance;
- workload identity;
- least-privilege authorization;
- central secret management and rotation;
- TLS and protected service authentication;
- network ingress/egress policy;
- SSRF/private/metadata endpoint denial;
- sandbox isolation for executable content;
- malware/content inspection for artifacts;
- dependency, secret, malware and provenance scanning;
- provider/tool confused-deputy resistance;
- tenant/data-class enforcement;
- immutable or tamper-evident audit;
- budget/rate/abuse control.

### 8.1 Cryptographic baseline

Target baseline:

- TLS 1.2 minimum; TLS 1.3 preferred;
- encrypted authoritative database storage;
- encrypted backups;
- encrypted artifact storage for non-public data;
- central KMS/secret manager integration;
- environment-separated keys;
- rotation support and access audit.

### 8.2 Vulnerability response target

| Severity | Target |
| --- | --- |
| Critical | Immediate triage; contain/mitigate within 24h |
| High | Remediate within 7 days |
| Medium | Remediate within 30 days |
| Low | Risk-based backlog |

Active exploitation, cross-tenant exposure, key compromise, or fail-open
security behavior overrides the nominal timing.

## 9. Reliability architecture

The reliability doctrine is:

> Preserve canonical truth first. Degrade optional capability second. Never
> manufacture success.

Failure domains explicitly covered by the plan:

- process crash;
- node/host loss;
- failure-domain/AZ loss;
- database failure;
- derived retrieval failure;
- model provider outage;
- external tool outage;
- network partition;
- deployment regression;
- credential/key dependency;
- operator error;
- regional outage.

Required mechanisms:

- separate liveness/readiness;
- bounded retries with jitter for retry-safe work;
- circuit breakers;
- idempotency;
- execution fencing;
- bulkheads;
- queue backpressure;
- explicit timeouts;
- graceful drain;
- durable resume;
- degraded-mode matrix;
- canary rollback.

## 10. SLO architecture

SLO values below are **targets, not claims**.

| SLO | Target |
| --- | --- |
| Customer API availability | 99.95% monthly |
| Acknowledged conversation-write success | 99.99%, with zero accepted lost writes |
| Interactive admission latency | p95 <= 500ms before model execution |
| First durable progress for admitted interactive AI | p95 <= 5s |
| Durable operation restart/resume | 99.9% |
| Privileged action audit evidence | 99.99% |
| Canary rollback decision after breach evidence | <= 10 minutes |
| Scheduled backup success | >= 99% |
| Scheduled restore drill | 100% within declared RTO |

No SLO becomes "green" merely because the target appears in this document.
Production telemetry must measure it over the declared window.

### 10.1 Error budgets

Error budgets are operational decision inputs.

If burn rate exceeds policy:

1. stop risky release promotion;
2. prioritize reliability work;
3. shed optional/background load;
4. preserve canonical write integrity;
5. invoke rollback when the canary controller's policy requires it.

## 11. Disaster recovery

### Tier 0 — canonical authority

Examples:

- Mongo canonical records;
- operation/conversation state;
- governance approvals;
- tool receipts.

Target:

- RPO 0 for acknowledged commits inside active replicated region;
- region-loss recovery target RPO <= 5 minutes;
- RTO <= 30 minutes.

### Tier 1 — durable artifacts/evidence

Examples:

- artifact payloads;
- release evidence;
- durable audit archives.

Target:

- RPO <= 15 minutes;
- RTO <= 60 minutes.

### Tier 2 — rebuildable derived state

Examples:

- vector indexes;
- caches;
- search projections.

Target:

- rebuildable;
- RTO <= 4 hours or defined by capacity model.

### 11.1 Backup is not recovery

A successful backup job is not DR proof.

Required recovery evidence includes:

- encrypted backup;
- independent backup inventory;
- isolated restore;
- integrity validation;
- service reconstruction;
- derived-index rebuild;
- measured RPO/RTO;
- recorded drill receipt.

Restore drills are quarterly. A region-loss exercise is annual.

## 12. Capacity, fairness, and overload

Enterprise load control must protect both tenants and system integrity.

Required budgets:

- global concurrency;
- per-tenant concurrency;
- provider concurrency/rate;
- tool concurrency/side-effect count;
- queue depth;
- queue age;
- input/output tokens;
- cost;
- storage;
- external writes;
- agent depth;
- background worker count.

### 12.1 Overload order

When capacity is exhausted:

1. deny unsafe/unauthorized work;
2. defer low-priority background work;
3. shed optional enrichment when policy permits;
4. use compliant fallback capacity;
5. return typed overload/degraded response;
6. preserve already acknowledged canonical writes.

Interactive and large background workloads must use separate capacity pools or
equivalent bulkheading.

## 13. Observability

Every cross-plane operation should correlate:

- `trace_id`;
- `operation_id`;
- `execution_id`;
- `tenant_id`;
- `release_id`.

### Required telemetry

- RED metrics for service APIs;
- USE metrics for workers/stores/queues;
- provider latency/error/quality/cost;
- tool admission/outcome/idempotency;
- canonical repository latency/error/conflict;
- stream reconnect/gap/backpressure;
- retrieval freshness/quality/citation verification;
- canary SLO state;
- backup freshness and restore drills.

### Logging rule

Production logging is content-minimized.

Raw prompts, memory content, secrets, restricted payloads, and complete tool
outputs are not normal telemetry. Governed diagnostics require explicit mode,
access, retention, and audit.

## 14. Incident management

Severity model:

- **SEV0** — security breach, tenant isolation failure, data integrity/loss risk;
- **SEV1** — major customer outage;
- **SEV2** — partial production degradation;
- **SEV3** — localized defect.

Every SEV0/1 incident requires:

- incident commander;
- time-stamped event log;
- mitigation owner;
- communication owner;
- explicit recovery criteria;
- post-incident analysis;
- corrective actions with owner and due date.

Mitigation takes precedence over perfect root-cause analysis during active
impact.

## 15. Release architecture

The release path is:

```text
source revision
   -> deterministic build
   -> SBOM/provenance
   -> structural validators
   -> focused tests
   -> integration/golden journeys
   -> migration preflight
   -> staging
   -> canary/progressive rollout
   -> live SLO evidence
   -> promote OR automatic rollback
```

Security/authority failures are non-overridable blockers.

### 15.1 Database changes

State schema changes use:

```text
expand
 -> deploy compatible readers/writers
 -> migrate/backfill
 -> prove new state
 -> switch authority
 -> contract/remove old shape
```

Rollback and forward-fix rules must be known before migration begins.

## 16. Required enterprise journeys

The system is not enterprise-complete until the following are automated:

1. authenticate -> create conversation -> multi-turn AI -> durable reconstruction;
2. retrieval answer -> evidence/citation verification -> accepted response;
3. tool proposal -> approval -> exactly-once side effect -> receipt;
4. artifact upload -> scan -> parse -> use -> export/delete lifecycle;
5. provider outage -> compliant failover or explicit degraded response;
6. engine restart -> durable resume -> canonical completion;
7. client disconnect -> reconnect without duplicate completion;
8. tenant export/delete -> cross-plane propagation and physical acknowledgement;
9. overload -> fair defer/shedding -> canonical writes preserved;
10. bad release -> canary breach -> automatic rollback;
11. backup restore -> isolated verification -> system reconstruction;
12. privileged operator action -> JIT authority -> immutable audit -> expiry.

## 17. Operating model

### Service owner

Owns:

- service health;
- SLO;
- runbooks;
- capacity;
- defect backlog.

### Architecture owner

Owns:

- canonical authority boundaries;
- dependency direction;
- contract evolution;
- architecture exceptions.

### Security owner

Owns:

- threat model;
- security exceptions;
- containment;
- key/credential incidents.

### Data/governance owner

Owns:

- data classification;
- lifecycle;
- retention;
- export/delete;
- privacy controls.

### Release owner

Owns:

- promotion;
- rollback;
- release evidence.

## 18. Mandatory runbooks

At minimum:

- tier-0 database outage/failover;
- provider outage/failover;
- engine overload/backpressure;
- suspected cross-tenant exposure;
- compromised credential/key rotation;
- failed deployment/rollback;
- ambiguous tool side effect;
- operation stream corruption/gap;
- backup restore/region loss;
- malware artifact quarantine;
- governance deletion/export failure;
- capacity exhaustion and tenant fairness.

A runbook that has never been exercised is not accepted as production evidence.

## 19. Review cadence

**Daily**
- automated SLO/error-budget and security signal review.

**Weekly**
- operating review: incidents, capacity, degraded dependencies, backlog.

**Monthly**
- SLO/error-budget review;
- privileged access review;
- dependency health;
- restore evidence freshness.

**Quarterly**
- restore drill;
- threat-model review;
- failover/game day;
- architecture-debt review.

**Annually**
- region-loss exercise;
- enterprise control-baseline review.

## 20. Sixteen implementation workstreams

The machine contract is authoritative for dependency edges and exit criteria.

### ENT-01 — Runtime cell and service identity

Build production ingress, service identity, multi-replica readiness, and
failure-domain-safe topology.

### ENT-02 — Tenant and privileged access model

Complete RBAC/ABAC, JIT admin, break glass, cross-tenant adversarial tests.

### ENT-03 — Canonical state HA and transactions

Prove quorum topology, transaction capability, and zero accepted lost writes.

### ENT-04 — Backup, PITR, disaster recovery

Automate encrypted backup, isolated restore, and measured RPO/RTO.

### ENT-05 — SLO/SLI and error-budget plane

Make every enterprise SLO measurable and consumed by alerts and release policy.

### ENT-06 — Capacity, fairness, overload

Build per-tenant/provider/tool budgets, queue age limits, bulkheads, and load
evidence.

### ENT-07 — Service-to-service zero trust

Move protected production calls to short-lived workload identity and mutually
authenticated transport or equivalent.

### ENT-08 — Security operations and audit

Prove privileged-action audit completeness, alert routing, compromise drills,
and expiring exceptions.

### ENT-09 — Production observability and incident command

Build RED/USE dashboards, trace continuity, paging, and exercised SEV runbooks.

### ENT-10 — Progressive delivery and rollback

Prove canary rollout, automatic rollback, and migration rehearsal.

### ENT-11 — Data lifecycle and privacy operations

Prove retention/export/delete/hold across canonical state, projections, and
backups.

### ENT-12 — Enterprise golden journeys

Automate all system journeys across restart, failover, overload, rollback, and
recovery.

### ENT-13 — Supply chain and release provenance

Require SBOM, signed/provenanced artifacts, dependency/malware/secret gates.

### ENT-14 — Compliance-ready control evidence

Produce a control inventory and evidence retention model without claiming
certification.

### ENT-15 — Performance and cost engineering

Define and prove production envelope, scale thresholds, and cost per journey.

### ENT-16 — Enterprise production acceptance

This is the only promotion step that may set `production_claim=true`.

It requires:

- zero open P0 enterprise workstreams;
- exact-head independent architecture receipt;
- current SLO evidence;
- current restore evidence;
- current security/supply-chain evidence;
- capacity evidence;
- canary/rollback evidence.

## 21. Definition of enterprise-complete

### Architecture-plan complete

The plan may be signed complete when:

- the enterprise contract parses;
- every source contract exists;
- all 27 construction planes map into enterprise domains;
- runtime services match the application manifest exactly;
- SLO, DR, security, tenancy, capacity, observability, release and operating
  sections pass deterministic validation;
- exact-head evidence can be independently rehashed;
- CI runs enterprise validation beside existing architecture/construction/state
  gates.

### Production complete

The **system** may be signed complete only when:

- `production-ha` requirements are proven in a production-like environment;
- all enterprise journeys pass;
- SLO evidence is current;
- backup/restore evidence is current;
- no unexpired P0 security/architecture exception remains;
- load/capacity envelope is proven;
- release canary and rollback are proven;
- supply-chain evidence is current;
- the independent exact-head enterprise receipt is green.

Until then:

```text
plan_complete     = true
production_claim  = false
```

That distinction is mandatory and fail-closed.

## 22. Operator validation

```bash
python scripts/check_enterprise_system_architecture.py
python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_state_topology.py
python -m skeleton app check
```

Exact-head CI additionally emits and independently verifies the enterprise
architecture evidence receipt.

## 23. Architecture decision rule

When adding a new subsystem, ask in this order:

1. Which existing enterprise domain owns it?
2. Which canonical capability plane owns it?
3. Which state authority does it read/write?
4. Which tenant/security boundary applies?
5. What is its degraded behavior?
6. What is its SLO?
7. What is its capacity budget?
8. What is its recovery class?
9. What telemetry and runbook prove operation?
10. What exact evidence permits production promotion?

If those answers are not explicit, the subsystem is not enterprise-ready.

---

**Architecture signoff:** This document and its machine contract define the
complete enterprise system target and implementation DAG. They do **not** claim
that production runtime evidence has already satisfied those targets.
