# Consumer installation and runtime verification — 2026-10-23

Status: implementation candidate; refreshed-runtime qualification in progress.
The operator explicitly requested all tests and live installation. Earlier
source-only observations remain historical and are not acceptance evidence.

## Installed topology

The production Compose installation uses the canonical engine, application API,
Nginx web export and authenticated MongoDB, with fresh private configuration and
an explicitly bootstrapped owner. Existing volumes, signing identities and local
model weights are preserved. No hosted model calls or commercial ROM downloads
are part of verification.

Initial observation: all four services became healthy; authenticated readiness
reported conversation storage, engine, models and crawler available. A pinned
local GGUF and executable were hash verified. A real local-model conversation
completed, an exact replay returned the same response, and another account could
not read the owner's thread. A separate reviewed conversation completed all four
provider stages. During reviewed inference and the broader tests, 48 concurrent
readiness/model reads at concurrency eight all returned HTTP 200; the observed
p95 was 523.62 ms. This is a bounded observation on this VM, not a service-level
guarantee.

## Repairs and verification scope

- Local inference keeps canonical architecture, governance, admission, settlement,
  context compilation and physical-worker drain boundaries. Native artifact reads
  reject symlinks, descriptor replacement, growth, truncation and malformed JSON.
- Chat regressions exercise durable prepared commands, exact replay, lease fencing,
  database timestamps, storage crash recovery, cancellation and immutable context.
- Galaxy respects explicit output limits, keeps partial source durably, distinguishes
  artifact completion from generation, and enforces existing roles and scoped build
  ownership across main and independently mounted sibling routes.
- Production build artifacts use `/app/data/builds_vault` on the existing backend
  volume, with the safety headroom retained. Local operational journals are excluded
  from release build contexts and Git.
- Accepted queued gameplay retries existing admission on authorized owner polling;
  task deduplication, global physical credits and source reauthorization remain in
  force. No autonomous queue scheduler is claimed.
- Empty begin-failure preview recovery retains a typed successful rollback and
  base-state proof; committed previews still require every phase receipt. Native
  authority evidence exposes aggregate usage on its owning bundle. Compensation
  pins the exact succeeded effect head atomically and preserves replay and
  quarantine denials.
- Production web builds exclude host Metro transforms. Metro cache identities
  include public endpoint inputs and resolved public manifest values so changes
  cannot silently reuse the previous installation's baked service addresses.
- A real original maze project was created and edited, simulated and trained for
  two bounded episodes. Source export matched its SHA-256. A consent-bound crawler
  captured one document from example.com using two requests and 1,154 bytes.

## Test evidence

The session retains JUnit, command logs, image build receipts and secret-free
workflow summaries under `/workspace/scratch/consumer-readiness-2026-10-22`.
Private credentials and raw operational state are excluded from the repository.
A final curated evidence record will identify completed checks and limitations.

Current verified groups include 746 chat tests and 12 subtests, the exact
22-file inference manifest (322 cases across isolated runs), 116 changed
inference/composition tests, 76 studio/learning/delivery tests, model-artifact
security tests, and frontend test/type/lint groups. Focused native follow-ups
passed 49 authority, 17 compensation, 18 simulation and 59 preview cases. Four
real-Metro configuration regressions passed. Three real Mongo shared-authority
and failure-recovery tests passed without skips against a disposable isolated
replica set; application database failpoints were never enabled. The live
Galaxy probe passed 23 cases, including five real deployment checks: viewer
creation was denied, and an explicit three-file partial build retained exactly
three readable artifacts with no completed phase or surviving worker. These groups overlap broader
suite runs and must not be summed into a unique-test total. The active repository
inventory includes conventional tests and embedded canonical suites; satellite,
research and mirrored duplicate test copies are tracked separately.

## Release gates still requiring closure

- The complete active test inventory is being exercised. Retained failures,
  collection errors and partial timed-out batches are not successful evidence.
- Some historical deployment tests require an old prebuilt project or a different
  deployment layout. A long original-ROM training case exceeded a short bounded
  observation; its larger isolated run and retained process-crash investigation
  must be accounted for explicitly.
- The frontend known-advisory gate reports affected `braces@3.0.3` and
  `node-forge@1.4.0`, with no published patched versions observed. Local patches
  are not a substitute for passing the declared release gate.
- The initial web image contained stale API addresses due to an imported Metro
  cache. Its replacement must pass
  real browser login, model use and reload checks against the current topology.
- The refreshed backend proved Galaxy viewer denial and persistent bounded artifact
  admission. Final images must still prove complete browser login, local-model chat,
  matching-policy AI play, saved-state recovery and all service health checks.
  Human play has produced a real frame and positive transition after replacement.
- A small CPU model demonstrates functional inference, not studio-level creative
  quality. Native consoles, firmware, SDKs, external services and other operating
  systems require their own actual prerequisites and qualification.

No production, enterprise, security or universal-console signoff is advanced by
this record.
