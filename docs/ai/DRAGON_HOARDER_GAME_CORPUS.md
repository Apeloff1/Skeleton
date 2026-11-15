# Dragon Hoarder — game corpus and physical archive expansion

This is a review-only layer stacked on #5438. It does not replace the canonical crawler scheduler, archive grants, source policy, Hoag reference checks, or Wiki approval pipeline.

## Capacity is not a session count

The prior nominal 1,048,576 expedition reservations are not physical storage. The new private BulkArchive primitive supports 1–64 operator-provisioned filesystem volumes, with individually configured compressed payload budgets of 1 GiB–1 PiB. These are configuration bounds only. Each volume has a separate SQLite ledger, scope-bound SHA-256 identity, compression, deduplication within the owner and volume, transactional insertion/deletion and exact read verification. Filesystem free space is measured on admission, and at least 1 GiB plus conservative page/WAL headroom is reserved. Shared filesystems cannot be counted twice. SQLite database/WAL overhead is not included in the compressed payload budget; an OS quota, redundancy, and independent disk stress tests are still required.

Illustrative planning, NOT benchmark results:

| Retained pages/revisions | Average compressed bytes | Payload only |
|---:|---:|---:|
| 10 million | 32 KiB | 305 GiB |
| 100 million | 32 KiB | 2.98 TiB |
| 1 billion | 32 KiB | 29.8 TiB |
| 1 billion | 128 KiB | 119.2 TiB |

Indexing, manifests, historical variants, database slack, backups, and redundancy must be budgeted additionally. For a personal install start with available local storage; for a dedicated collector, mount separate volumes. No data payload should be committed to Git.

The bulk primitive is deliberately not yet used to relocate Mongo source bytes: canonical reference accounting, source grant revalidation, retention/deletion reconciliation, recovery after dual-write crashes, manifest replication, cryptographic backup and operator lifecycle remain release blockers. No raw-data API is exposed. Scope separation is not encryption. Logical object deletion does not guarantee secure disk erasure. Use operator-controlled private volumes; hostile same-UID processes are out of scope.

## Game coverage and change discovery

The owner catalogue supports a nominal 2 million game identities, 50 million observations and 512 distinct source identities per game, subject to actual storage and SQLite qualification. Game identity is namespace plus external ID; no automatic cross-provider merge. Title aliases are FTS-indexed. Each source retains its latest observed metadata independently from its older immutable observations. Stage is an unverified report, not a global current truth. Source types include official/community wikis, storefronts, release feeds, patch notes, developer blogs, manuals, mod catalogues, technical references, accessibility, preservation, esports, community guides, engine docs and localization. Language is part of source identity. Release, early-access and update observations tighten review cadence. Replay does not shift deadlines; differing payload under the same event identity is rejected.

Configure a private separate database via SKL_DRAGON_GAME_CORPUS_DB_PATH; initial creation on editor observation requires SKL_DRAGON_RUNTIME_BOOTSTRAP=1. Existing file must be private; FTS5 is required. Existing authenticated knowledge router endpoints:

- POST /knowledge/game-corpus/observations (editor/admin).
- GET /knowledge/game-corpus/search?q=...
- GET /knowledge/game-corpus/due (editor/admin, review planning only).
- GET /knowledge/game-corpus/{game_id}/sources (keyset page).
- GET /knowledge/game-corpus/{game_id}/history (keyset page).
- GET /knowledge/hoag-archive?game_catalogue=true&q=... (optional catalogue title hints beside canonical reviewed and historical source results).

Metadata is never automatically evidence, prompt context, training data, permission to crawl or Wiki approval. URL identifiers never trigger network requests. Source discovery adapters, approved network scheduling/retry/robots/license checks, catalogue lifecycle and erasure/export, source-to-payload reference graph, full semantic corpus indexing, cross-provider identity reconciliation, UI and local Jeeves retrieval of qualified game-scoped passages remain follow-up integration work. Do not count the catalogue as populated or automatically refreshed merely because schema exists.

## Qualification

Focused regression: python -m pytest backend/tests/test_dragon_hoarder_game_corpus.py (with repository backend import environment). Verify all inherited archive/crawler, backend, security, repository and frontend gates at exact head. Test real independent filesystems, WAL contention, disk-full, process-kill recovery, mounted volume replacement, permission/revocation transitions and restoration before production enablement. The configured maximums are neither measured throughput nor demonstrated capacity. No merge or release authorization.
