# Six-month and annual production: Jeeves · Builder · Dragon

**Implementation:** `annual_production.py`, `annual_worker.py`,
`annual_supervisor.py`, `annual_handoff.py`, and subsystem adapters
`skeleton/jeeves/annual_production.py`,
`skeleton/automation/builder_annual_production.py`,
`skeleton/ai/webcrawler/dragon_annual_production.py`.

This design is for **long-lived, restartable production identity and backend
commit safety**—not keeping one Python/LLM process alive for a year. A process
supervisor must restart ordinary bounded worker steps. Producers must use
their existing canonical model/graph/research owners.

## Runtime contract

| Plane | Owns execution | Required evidence before checkpoint | Cannot do |
| --- | --- | --- | --- |
| Jeeves | Governed Jeeves model/story/world worker | Canonical scene/canon/story checkpoint digest and external continuity verification | Fabricate story completion or replace user voice |
| Builder | Existing graph/build/installer worker | Content-addressed artifact and build verification from canonical builder | Treat a queued CI run or uncompiled source as complete |
| Dragon | Existing crawler/almanac/weight-review worker | Reviewed legal source, almanac or qualified training evidence | Promote unchecked knowledge, auto-learn copyrighted material without authority |
| Shared annual control | SQLite `AnnualProductionStore` | Short worker lease, exact next sequence, verified external evidence digest | Execute models, authorize work or bypass studio access controls |
| Month-cycle client | AsyncStorage and foreground reconciliation | Backend status/read-only canonical response | Keep executing with app closed or grant permission |

The backend service must explicitly bind *real* host callbacks. The default
annual runners do not provide fake model outputs, tests or source receipts.

```python
from time import time
from pathlib import Path
from skeleton.automation.annual_production import AnnualProductionStore
from skeleton.automation.annual_supervisor import AnnualProductionSupervisor
from skeleton.jeeves.annual_production import make_jeeves_annual_runner
from skeleton.automation.builder_annual_production import make_builder_annual_runner
from skeleton.ai.webcrawler.dragon_annual_production import make_dragon_annual_runner

# Provision a persistent, backed-up local volume outside ephemeral containers.
store = AnnualProductionStore(Path("/var/lib/skeleton/annual-production.db"))
# An authenticated host creates the 183/366-day job with hashes of its
# approved objective and current authority; see store.enroll.
# The following MUST be provided by actual governed backend owners:
runners = {
    "jeeves": make_jeeves_annual_runner(
        store, run_authorized_step=jeeves_backend_one_quantum,
        verify_canonical_receipt=verify_jeeves_canon),
    "builder": make_builder_annual_runner(
        store, run_build_graph_quantum=builder_backend_one_quantum,
        verify_build_artifacts=verify_builder_artifact),
    "dragon": make_dragon_annual_runner(
        store, run_reviewed_research_quantum=dragon_backend_one_quantum,
        verify_reviewed_knowledge=verify_dragon_almanac),
}
host = AnnualProductionSupervisor(
    store, runners, authority=load_current_approved_grant_digest)
report = host.sweep(owner=worker_instance_id, now=time(), limit=8)
```

The names in this example deliberately represent **host-provided** functions;
they are not defined here. Production deployment cannot proceed until the
existing Jeeves, Builder and Dragon runtime owners supply their real
implementation, authenticated grants and external evidence verifiers.

## Six months and one year

`AnnualProductionStore.enroll(..., horizon_days=183|366, ...)` binds the
approved original objective digest and an independently established
authorization grant. Both horizons keep the production job registered beyond
a crash or disconnected UI. Horizon is planning metadata, **not an automatic
authority extension** and not a forced deletion timer.

Each worker can hold only a short (1–3,600 second) fenced lease. Long
steps call `WorkQuantum.heartbeat(seconds)` before expiration, but each
heartbeat is bounded by the current grant expiry. When an old worker wakes
after expiry or a replacement claim, its token and epoch cannot advance
the durable checkpoint.

Stable idempotency keys derived from **production ID + next checkpoint
sequence** make an ambiguous work result reconcilable by a new worker without
inventing a second canonical operation. A backend executor must honor these
keys: the shared control plane cannot enforce remote exactly-once side effects
on an external system by itself.

Every next checkpoint is committed transactionally with the cursor and a
digest linking to the prior checkpoint. `verify_chain()` streams the full
chain without loading all receipts into memory. Receipts retain identities,
state digests, evidence digests, epochs and timestamps but never user content
or credentials. Nothing is automatically deleted merely because a production
is months old. Disk quotas, archival/backup policy and restore drills remain
deployment obligations.

## Explicit grant renewal, without hidden self-authorization

`store.renew_authority(..., verify_approval=trusted_backend_verifier)`
requires an external approval verification callback. It extends expiry,
atomically invalidates old worker lease tokens by advancing their epoch,
and appends an immutable, hashed authority-rotation receipt. Work runners
check `verify_authority_chain()` before executing. Expired grants cause
jobs to disappear from due admission **without deleting their checkpoint
history**. Only approved extension can re-admit them; terminal work remains
terminal.

The verifier must validate signed approval, issuer, subject, owner, scope,
expiry and revocation against the actual authoritative consent/policy store.
A hash string or frontend request is NOT proof of authority. The runtime
does not silently renew expired studio permissions.

## Cross-plane source → canon → artifact provenance

`AnnualHandoffLedger` records a reviewed digest handoff tied to an
existing *current* source checkpoint and the destination objective digest.
Use Dragon→Jeeves for reviewed research, Jeeves→Builder for accepted
world/scenes/asset instructions, Builder→Dragon for measured training evidence.
A handoff does NOT authorize a consumer's next unit of work; the receiving
subsystem validates its own rights and canonical source material.

Handoff records form their own digest chain, survive SQLite restarts,
reject tampered or stale source checkpoints and support bounded paged reads.
The supplied review callback is responsible for verifying legal rights,
provenance and semantic/canon correctness; this module cannot infer them.

## Scheduling, shutdown and failure handling

- The host invokes `AnnualProductionSupervisor.sweep(..., limit=1..100)` per
  bounded cycle. It admits at most one quantum per production per sweep,
  keeps three subsystems separate and never spins on a failing job.
- A supervisor must be deployed via a real **restartable service** (systemd,
  Windows service, Kubernetes controller, or a trusted operational scheduler).
  On startup it reopens the **same persistent database** and scans due jobs.
- If a worker has ambiguous results, its short lease remains held until
  expiration. A replacement must first query the canonical executor with the
  stable idempotency key; it must not blindly rerun side effects.
- Each verified nonterminal quantum releases its lease with a short fair
  yield, allowing other projects to advance. Terminal completion requires
  canonical verified evidence and does not follow from an expired observation.
- WAL mode is configured when provisioning. Do not put the SQLite database
  on an unreliable network filesystem or rely on an ephemeral container
  volume. Multi-host deployment needs an actual shared transaction store
  (e.g. an independently designed SQL/Mongo CAS implementation), not two
  unsynchronized local SQLite copies.
- Back up database + WAL together using SQLite's online backup API or safe
  snapshots, then **restore and verify** production checkpoint and grant
  chains in an isolated environment before promotion.

## Verification and remaining work

`tests/test_annual_production.py` exercises six- and twelve-month horizons,
stale leases, 800 checkpoint commits, corruption and worker turnover.
`tests/test_annual_worker.py` executes real injected Jeeves/Builder/Dragon
quantum mocks and proves stale workers cannot sign a late checkpoint.
`tests/test_annual_authority.py` tests audited renewal and lease
invalidation. `tests/test_annual_supervisor.py` covers fair three-plane
admission and crash restart. `tests/test_annual_handoff.py` verifies
cross-plane evidence linkage and corruption detection. They run as real SQLite
tests inside the **existing** Merge Readiness workflow—no new CI job.

**These tests cannot establish physical year-long endurance.** Still needed:
binding actual model checkpoints/game build graphs/Dragon learning owners,
persistent worker process supervision, signed approval integration, network
partition testing, model state schema upgrades, encrypted/offsite backup,
restore after filesystem damage, worker/host failover, disk capacity trends,
realistic model and GPU/thermal contention, and unattended multi-day
integration tests. Do not represent a simulated 366-day timestamp jump as
a real year of production execution.
