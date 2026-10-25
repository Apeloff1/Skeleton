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
not read the owner's thread.

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
- A real original maze project was created and edited, simulated and trained for
  two bounded episodes. Source export matched its SHA-256. A consent-bound crawler
  captured one document from example.com using two requests and 1,154 bytes.

## Test evidence

The session retains JUnit, command logs, image build receipts and secret-free
workflow summaries under `/workspace/scratch/consumer-readiness-2026-10-22`.
Private credentials and raw operational state are excluded from the repository.
A final curated evidence record will identify completed checks and limitations.

Current verified groups include 746 chat tests and 12 subtests, 116 changed
inference/composition tests, 76 studio/learning/delivery tests, model-artifact
security tests, and frontend test/type/lint groups. These groups overlap broader
suite runs and must not be summed into a unique-test total. The active repository
inventory includes conventional tests and embedded canonical suites; satellite,
research and mirrored duplicate test copies are tracked separately.

## Release gates still requiring closure

- The complete active test inventory is being exercised. Retained failures,
  collection errors and partial timed-out batches are not successful evidence.
- Some historical deployment tests require an old prebuilt project or a different
  deployment layout. Three chat cases require an isolated Mongo replica set with
  test failpoints; the application database must not receive those failpoints.
- The frontend known-advisory gate reports affected `braces@3.0.3` and
  `node-forge@1.4.0`, with no published patched versions observed. Local patches
  are not a substitute for passing the declared release gate.
- The initial web image contained stale API addresses. Its replacement must pass
  real browser login, model use and reload checks against the current topology.
- The refreshed backend must prove Galaxy role/owner isolation, persistent artifact
  admission and human-to-AI queued-play recovery before those installed behaviors
  are considered verified.
- A small CPU model demonstrates functional inference, not studio-level creative
  quality. Native consoles, firmware, SDKs, external services and other operating
  systems require their own actual prerequisites and qualification.

No production, enterprise, security or universal-console signoff is advanced by
this record.
