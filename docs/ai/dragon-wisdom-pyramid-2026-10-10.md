# Dragon knowledge pyramid rollout — 2026-10-10

Branch: feat/dragon-wisdom-review-20261010 (draft PR #3605).
This is a bounded implementation increment, not a completed product signoff.

## Canonical ownership

| Stage | Authority and new integration |
| --- | --- |
| Companion | Existing crawler owns acquisition, consent and custody. New read-only recrawl intents do not grant execution. |
| Almanac | Existing ReviewedKnowledgeStore owns source revisions, exact citations, license scopes, confidence and retractions. |
| Wiki | A trusted independent reviewer checks current citations, conflicts, distinct source groups and explicit review evidence. Reviewer identity must be authenticated by the embedding service. |
| HOAG | Read-only owner-scoped projection shows currently eligible advisory topics with expiry and evidence hashes. |
| Permanent memory | Promotion records advisory eligibility only. No global/model-memory write or training grant exists. |
| Release | Gold-master and independent rights authorities remain unchanged. |

The new derived journal stores only source and note identifiers, review and
revision digests, recrawl states and decisions. It does not retain raw scraped
text, conversation transcripts, original game assets or ROM files.

## Evidence flow

The append-only SQLite ledger verifies contiguous owner-specific sequence
numbers, canonical JSON, prior hashes and exact content digests on every read.
Mutations use BEGIN IMMEDIATE and monotonic timestamps. Per-owner maximum:
10,000 events, with an 8 KiB serialized event cap.

An accepted Wiki review needs two different supporting source IDs and two
different independence groups for the specific game mechanic, no challenging
citation, a currently valid canonical source root and no outstanding recrawl.
Review lifetime is at most 30 days. Future-dated citations cannot be approved.

A recrawl request holds a source ID, expected canonical revision, reason and
priority. It is only a scheduler handoff. Completion requires a genuinely new
canonical revision admitted through the original knowledge store; the worker
cannot self-certify source acquisition. An outstanding order suspends the
affected approved memory.

Human-approved promotion requires a valid accepted Wiki receipt, fresh root
and no outstanding recrawl, revocation or later adversarial challenge.
HOAG checks these again at read time. A retraction, changed source revision,
revocation, expiry or challenge automatically hides the affected eligible
memory without erasing the historical review chain.

The system is advisory. No evidence hash is a digital signature. A hostile
database administrator could rewrite local hash chains unless production
checkpoints are externally signed and anchored.

## App integration

Configure SKL_DRAGON_KNOWLEDGE_DB_PATH to an existing, durable, reviewed
SQLite knowledge store. Absent storage yields 503, not a new empty database.

Authenticated GET endpoints:
- /api/dragon-academy/knowledge/hoag — expiry-bound reviewed topics, source
  revision hashes, review evidence root, no underlying source prose.
- /api/dragon-academy/knowledge/recrawls — order identifiers, reasons and
  priority; execution_authorized is always false.

The product route uses the existing verified Dragon Academy tenant/user
principal and returns private, no-store headers. It has no browser mutation
route for approval, memory, recrawl dispatch or source review.

The React Native companion polls HOAG with the authenticated account,
validates a strictly bounded advisory schema, clears invalid or stale data,
and renders the three stages with source independence counts and expiry.
Authentication failures do not fabricate successful knowledge promotion.

## Verification and operational acceptance

Committed test coverage includes ten knowledge ledger cases for restart,
independent sources, challenges, recrawl, source revisions, retractions,
revocation, isolation, corrupted history and stale citations. Additional
authenticated FastAPI HTTP tests cover tenant privacy and read-only behavior.
Frontend schema and view tests were added to the existing Dragon wisdom
verification script, and the Python module is included in Dragon CI.

Open requirements:
1. Independent reviewer identity credentials, conflict-of-interest checks,
   source custody and human approval receipt verification.
2. Live trusted crawler worker scheduling, resource admission, cancellation,
   recrawl acknowledgement and finite bounded retries.
3. The separate canonical AI memory store's consent, retention, revocation,
   deletion, rollback and training-policy hooks.
4. Externally anchored signed journal checkpoints and restore drills.
5. Real multi-console and contemporary-engine source ingestion with verified
   access rights, plus practical homebrew build/port/engine acceptance.
6. Exact-branch-head CI results, consumer device tests and release authority
   before merging the draft PR.

## Current implementation checklist

- [x] Derived Almanac/Wiki/HOAG event chain committed
- [x] Independent support, time and authority constraints committed
- [x] Recrawl intent, revision completion and revocation behavior committed
- [x] Authenticated read-only product adapter committed
- [x] Companion visualization and defensive parser committed
- [x] Focused Python, backend HTTP and frontend checks committed
- [ ] Exact-head hosted CI confirmed successful
- [ ] Production reviewer/crawler/memory services integrated
- [ ] Recovery/security/per-platform acceptance completed
- [ ] PR reviewed and merged to main

The checked items describe committed implementation, not verified deployment
or end-to-end autonomous knowledge acquisition.
