# Dragon Hoarder — game corpus and physical archive expansion

This is a review-only layer stacked on #5438. It does not replace the canonical crawler scheduler, archive grants, source policy, Hoag reference checks, or Wiki approval pipeline.

## Capacity is not a session count

The prior nominal 1,048,576 expedition reservations are not physical storage. The new private BulkArchive primitive supports 1–256 operator-provisioned filesystem volumes, with individually configured compressed payload budgets of 1 GiB–1 PiB. These are configuration bounds only. Each volume has a separate SQLite ledger, scope-bound SHA-256 identity, compression, deduplication within the owner and volume, transactional insertion/deletion and exact read verification. Filesystem free space is measured on admission, and at least 1 GiB plus conservative page/WAL headroom is reserved. Shared filesystems cannot be counted twice. SQLite database/WAL overhead is not included in the compressed payload budget; an OS quota, redundancy, and independent disk stress tests are still required.

Illustrative planning, NOT benchmark results:

| Retained pages/revisions | Average compressed bytes | Payload only |
|---:|---:|---:|
| 10 million | 32 KiB | 305 GiB |
| 100 million | 32 KiB | 2.98 TiB |
| 1 billion | 32 KiB | 29.8 TiB |
| 1 billion | 128 KiB | 119.2 TiB |

Indexing, manifests, historical variants, database slack, backups, and redundancy must be budgeted additionally. For a personal install start with available local storage; for a dedicated collector, mount separate volumes. No data payload should be committed to Git.

Physical staging now copies eligible canonical snapshots into a journaled chunk manifest and reconciles withdrawal/deletion through the existing scheduler. An opt-in dual-copy cold-primary lane now stages two separately mounted copies, validates physical probe receipts and readback, then atomically removes the Mongo snapshot and embedded replica while preserving the canonical metadata ledger. Active sessions and unqualified archives stay in Mongo. Expiry/withdrawal restores the primary before removing copies unless the canonical session was deleted. Production physical-device qualification, all lifecycle gates and operator deployment remain blockers. No raw-data API is exposed. Scope separation is not encryption. Logical object deletion does not guarantee secure disk erasure. Use operator-controlled private volumes; hostile same-UID processes are out of scope.

## Game coverage and change discovery

The owner catalogue supports a nominal 50 million game identities, 2 billion observations and 20 million distinct source identities per game, subject to actual storage and SQLite qualification. Game identity is namespace plus external ID; no automatic cross-provider merge. Title aliases are FTS-indexed. Each source retains its latest observed metadata independently from its older immutable observations. Stage is an unverified report, not a global current truth. Source types include official/community wikis, storefronts, release feeds, patch notes, developer blogs, manuals, mod catalogues, technical references, accessibility, preservation, esports, community guides, engine docs and localization. Language is part of source identity. Release, early-access and update observations tighten review cadence. Replay does not shift deadlines; differing payload under the same event identity is rejected.

Configure a private separate database via SKL_DRAGON_GAME_CORPUS_DB_PATH; initial creation on editor observation requires SKL_DRAGON_RUNTIME_BOOTSTRAP=1. Existing file must be private; FTS5 is required. Existing authenticated knowledge router endpoints:

- POST /knowledge/game-corpus/observations (editor/admin).
- GET /knowledge/game-corpus/search?q=...
- GET /knowledge/game-corpus/due (editor/admin, review planning only).
- GET /knowledge/game-corpus/{game_id}/sources (keyset page).
- GET /knowledge/game-corpus/{game_id}/history (keyset page).
- GET /knowledge/hoag-archive?game_catalogue=true&q=... (optional catalogue title hints beside canonical reviewed and historical source results).

Metadata is never automatically evidence, prompt context, training data, permission to crawl or Wiki approval. URL identifiers never trigger network requests. The expansion adds local-feed discovery adapters, durable queue recovery, explicit capture dispatch, source-to-session links, game-filtered Jeeves retrieval, and a cockpit. Operator-enabled unattended authorized feed fetching now exists; cross-provider identity reconciliation, unattended permissioned capture of new links, catalogue lifecycle and erasure/export remain follow-up work. Do not count the catalogue as populated or automatically refreshed merely because schema exists.

## Discovery and retrieval expansion

The taxonomy defines 864 distinct game knowledge source classes (the API reports the family count) with review cadence and priority. Steam application catalogues, RSS/Atom and normalized multi-provider manifests can be imported without network access. Bounded persistent queues use exact event identity, leases, recoverable commits and held outcomes. Import is not capture permission: owner/editor approval of the exact latest source observation is required for canonical dispatch. The existing crawler applies its network and capture rules. The release timeline separates current observations from immutable earlier versions.

The catalogue cockpit exposes discovery, source selection, release history, import progress and finite scheduler approval. Local Jeeves accepts an optional game identity for canonical current and historical retrieval; historical evidence retains exact archive pins and is never promoted automatically to reviewed Wiki truth.

Indexes now include FTS title aliases, release facets and keyset backfill, scope-bound term routes, rare-term routes, multilingual Unicode subword scores, BM25, phrase/title boosts, passage digests and bounded reciprocal rank fusion. The optional semantic lane uses local ONNX embeddings, int8 quantization, eight eight-bit random-hyperplane LSH tables, one-bit multiprobe and bounded cosine reranking. Separate current and historical generation workers now cover every nonblank overlapping 768-character window of qualified retained text at a 512-character stride, in independently admitted batches of eight. The sampled lane remains a fallback. Index generations publish only after coverage completes; query-side multiprobe and cosine reranking remain bounded and approximate, not exhaustive global ANN recall. Uncaptured, truncated, expired, or quarantined material is not indexed. Vector hits are reparsed against canonical source bytes, expiry and exact source policy before becoming historical chat context. The vector lane is disabled by default; failures preserve lexical results. Embeddings are derived sensitive data, not encryption. Protect Mongo and private volumes accordingly.

Set SKL_DRAGON_LOCAL_EMBEDDING_JSON only when the operator has verified local model and tokenizer bytes. The JSON fields are model, model_sha256, tokenizer, tokenizer_sha256, output, dimensions, max_tokens and threads. Optional numpy, onnxruntime and tokenizers must be independently installed and qualified. The model must satisfy the input/output tensor contract. This code ships no model weights and performs no model downloads.

Journaled physical manifests use 2 MiB blocks, at most 512 per document (1 GiB), deterministic placement, digest-checked reconstruction, deduplicated references and bounded garbage collection. Staging is explicit and grant-bound. A separate opt-in cold-primary operation requires two separately configured and measured storage copies; conventional staging is not backup verification. Crash recovery and cleanup are wired to the existing scheduler; real disk and concurrent workload qualification are still required.

## Viewable sources and cross-game source library

The source catalogue now covers gameplay and systems (combat, crafting, AI, economy, physics), locations and game worlds, wikis and guides, screenshots and artwork, maps and diagrams, trailers, gameplay walkthroughs, recorded broadcasts, audio references, PDF manuals, research and technical documents, development and modding, platforms, competitive play, live-service releases, preservation, rights and education. Categories are presentation and scheduling hints, not verified MIME types, source rights or automatic capture permissions.

A new owner-scoped source-locator FTS index covers title, locator and category, with persistent backfill and language/family/kind facets. Search results are current catalogue observations, not captured source contents. Source creation updates the index atomically and the per-game source counter is initialized from existing rows once, then maintained transactionally. Nominal admission rises to 20 million distinct source identities per game; the existing owner-wide observation limit still applies. This is not measured physical capacity.

The cockpit exposes original HTTPS links through explicit external navigation; a restricted YouTube watch identity can be normalized to a public video locator. It displays text from captured versions in-app only through the canonical treasury reader. Document metadata, exact captured text and source-diff windows bind owner, game, source, canonical session version, snapshot digest, content hash and live authorization. Each page or comparison rechecks authority; view responses are no-store and the cockpit clears displayed capture text within at most 30 seconds. Compare only the same canonical source URL. Reference links to video, images, audio and documents do not imply captured binary files. Explicit local media import separately seals immutable binary manifests using an expected SHA-256; the authenticated byte-range endpoint streams authorized sealed media. Inline native video/audio/images and browser playback are implemented; browser ingestion/playback is limited to 64 MiB. Native ingestion, long browser-video streaming, direct licensed remote acquisition, codec hardening, transcript ingestion and physical-scale qualification remain follow-up work. No remote iframe, active HTML, or DRM bypass is introduced.

## MMO and successor-generation qualification

Design leads (metadata candidate directories, not a claim of corpus contents):

- EVE developer documentation: https://developers.eveonline.com/docs/services/esi/overview/ ; https://developers.eveonline.com/docs/services/static-data/ ; https://developers.eveonline.com/docs/community/
- GTA VI official world and media directory: https://www.rockstargames.com/VI ; https://www.rockstargames.com/VI/only-in-leonida ; https://www.rockstargames.com/VI/launch-gallery
- Next-generation compute reference (Rubin is an AI infrastructure platform, not a verified gaming GPU specification): https://developer.nvidia.com/blog/inside-nvidia-rubin-gpu-architecture-powering-the-era-of-agentic-ai/

Planning targets are synthetic design envelopes rather than measurements of those games. The source taxonomy covers external tools and SDKs, fitting simulators, spatial navigation, industry and markets, versions, public APIs, static data and schemas, raid and persistent-world rules, rendering, streaming and procedural systems.

### Deployment switches

- SKL_DRAGON_WORLD_DISCOVERY=1 enables periodic authorized feed retrieval. Register exact HTTPS sources with finite editor grants. Supports normalized manifests, Steam catalogues, RSS/Atom, direct sitemap URL sets and an official EVE SDE build pointer. The pinned transport limits a network response to 4,000,000 bytes; larger feeds must be partitioned upstream or supplied locally. A sitemap can contain up to 50,000 URL entries subject to the byte bound. Each pulse enqueues at most four partitions. It cannot fetch unknown external destinations, unauthorized endpoints, private player records or automatically execute an external tool.
- SKL_DRAGON_DATASET_ROOT is a dedicated private directory, partitioned by owner/game hash into 256 SQLite shards. A version supports up to 100 million records subject to actual storage, with JSONL page-chain sealing, FTS and source/target relation indexes. Reported dataset records are unreviewed and currently separately browsable, not automatically injected into Jeeves.
- EVE public SDE JSONL/ZIP members may be imported with `python -m core.dragon_dataset_ingest --scope-json PRIVATE_SCOPE_FILE --game GAME_ID --source SOURCE_ID --observation-digest OBSERVATION_DIGEST --dataset systems --label BUILD --path LICENSED_EXPORT.zip --member mapSolarSystems.jsonl --acknowledge-retention-rights` after configuring private stores. Use the member name from the actual licensed archive. The CLI plans and reads exact pages twice, never extracts ZIP files to arbitrary paths. Authenticated ESI is not used.
- SKL_DRAGON_HOARDER_BACKUP_VOLUMES_JSON and SKL_DRAGON_HOARDER_BACKUP_MANIFEST_PATH configure the second custody lane. SKL_DRAGON_HOARDER_QUALIFICATION_PATH is a private operator receipt path. With both configured, run `python -m core.dragon_hoarder_qualification --probe-mib 64` on the deployment host. This writes and reopens real bytes on every device, checks isolation and deletes the probe objects. Disk topology identities do not prove distinct physical drives or power-loss independence. No maximum-capacity claim.
- SKL_DRAGON_ENABLE_COLD_PRIMARY=1 enables explicit terminal-only migration after a fresh probe. POST /knowledge/hoarder-primary/{session_id}/relocate and /restore use version fences and dual-manifest readback. Active Mongo runtime, grants, authority, derived indexes and binding metadata are deliberately not migrated. SKL_DRAGON_HOARDER_ALLOW_VOLUME_EXPANSION=1 enables additive mounted-volume expansion only; existing placements do not shift. Requalification is required after topology changes.
- Game routes now project exact catalogue capture bindings into indexed canonical session metadata. Historical and semantic search can route on game ID without limiting matching candidates to the recent 100 sessions; legacy recent bindings remain a temporary fallback during bounded backfill. Final selected membership and canonical source authority are independently checked. This is bounded retrieval, not an exhaustive global query.

## Qualification

Focused regression: python -m pytest backend/tests/test_dragon_hoarder_game_corpus.py backend/tests/test_dragon_hoarder_discovery_retrieval.py backend/tests/test_dragon_deep_archive.py backend/tests/test_dragon_source_library.py backend/tests/test_dragon_world_archive_expansion.py backend/tests/test_dragon_hoarder_media_cold.py (with repository backend import environment). Verify all inherited archive/crawler, backend, security, repository and frontend gates at exact head. Test real independent filesystems, WAL contention, disk-full, process-kill recovery, mounted volume replacement, permission/revocation transitions and restoration before production enablement. The configured maximums are neither measured throughput nor demonstrated capacity. No merge or release authorization.
