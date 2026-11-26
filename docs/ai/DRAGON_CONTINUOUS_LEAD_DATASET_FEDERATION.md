# Continuous Dragon lead and dataset federation

## Scale and evidence

The previous mod-seed directory offers 14,702 unique normalized locators. This branch additionally carries 200,704 distinct candidate Steam AppIDs and names in 21 versioned JSONL shards derived from the public jsnli/steamappidlist mirror. Every row, ordering, cross-shard range and source-controlled blob identity was inspected structurally. The original mirror blob is c44a5fcbd6f9260ceddc6005917812eaaf620137; each local shard has a pinned Git blob identifier. Twenty source records were excluded. The bundled AppIDs alone produce 200,704 distinct candidate storefront locators (over 13.6 times the earlier census); the 17-route projection gives 3,411,968 gross potential candidate paths, not independently verified URLs. Do not sum overlapping catalogues. The operative minimum remains 147,020 distinct persisted owner lead nodes measured at runtime. The repository-backed identity bundle is not evidence that those rows have been admitted into a running deployment, that all titles are current official releases, or that upstream data rights have been independently cleared.

The graph has nominal owner-scoped caps of 20 million unique locator nodes, 100 million provenance edges, 100,000 snapshot records, and 100 million rows per snapshot; these are logical admission limits, not physically qualified capacity. Static catalogue paths and discovered links remain unverified.

## Public source library

The 109 descriptors distinguish direct/public-download leads (27), manual download targets (2), authenticated API documentation (13), landing/discovery pages (9), policy-review targets (57), and a noncommercial-only archive (1). The latter and credential-required or landing-only targets cannot automatically become static import permissions. Never treat advertised counts as distinct combined rows. Terms, per-file rights, format and version are separately reviewed before importing or capture. The registry includes game releases, mod projects, preservation DAT and disc metadata, game-specific datasets, esports, media metadata, research and game development.

Research anchors:

- https://huggingface.co/datasets/FronkonGames/steam-games-dataset/tree/main/data — repository history advertises a Parquet export with 124,146 games; later README revision advertises 135,043. Neither count is an ingested count.
- https://huggingface.co/datasets/FronkonGames/steam-games-dataset/blob/main/games.csv — public CSV artifact metadata and SHA-256 pointer; resolve current exact revision and rights independently.
- https://www.kaggle.com/dsv/11017460 — 90,000+ Steam title snapshot.
- https://docs.modrinth.com/api/operations/searchprojects/ — paginated public project discovery documentation.
- https://github.com/libretro/libretro-database — platform, preservation and hash metadata.
- https://developers.eveonline.com/docs/services/static-data/ — official versioned static data, JSON Lines and YAML.
- https://docs.everef.net/datasets/ — EVE game-domain data archives.
- https://docs.speedrun.io/ — noncommercial archive terms; not automatically imported.

## Growth loop and custody

1. The editor enables owner-scoped lead metadata processing. A bounded scheduler bootstraps existing seeds plus dataset roots using a revision-bound cursor.
2. Approved feed subscriptions identify further leads. Their already-received normalized pages retain source-parent relationships. This does not expand network permission.
3. Canonical release queue settlement creates a durable outbox record in the same transaction. The lead worker consumes the outbox separately. New real provider-native Steam identities produce 17 candidate route families through durable expansion jobs; generated URLs retain candidate status.
4. Structured-data leads appear in the growing dataset-candidate index. Editor-reviewed registration permits bounded, finite locator-only metadata imports. Dynamic targets preserve parent identity and revoke open snapshots when their grant changes.
5. Local lawful exports can be projected through the streaming CLI or bounded NDJSON page API. A dataset snapshot retains source hash, expected count, page hashes and ordered chain; the CLI witnesses actual file bytes, whereas an API client declares the source hash. Duplicate locators deduplicate, but independent evidence and older versions are retained. Unsealed/revoked snapshots remain explicitly historical candidate evidence. No binary assets, private account rows or user histories are required.
6. Search, source relationships, source families, owner review disposition and due dates are indexed and exposed to the cockpit. These metadata do not become Wiki-approved facts, Hoag training inputs or crawl authority. Capture still uses the canonical crawler policy.

## Bundled admission

The cockpit exposes the bundle source, revision, shard count, observed progress, and finite owner-scoped source-use grant. After a reviewer verifies the relevant metadata rights and enables the graph, the bundle admission command enables a 30-day grant with a reviewed rights reference. The recovery scheduler admits up to 512 identity rows per pulse, verifying the pinned shard blobs, exact normalized pages, and ordered snapshot chain. Each storefront identity produces a durable follow-on expansion job; the expansion scheduler processes bounded batches and checks the source grant. Replays preserve identities and witnesses; revocation or expiry fences further work. No network access or training authorization follows from admission.

## Bulk admission example

After verifying the source terms, obtaining an authorized CSV export, and enabling the lead graph, use the backend environment:

```sh
python -m core.dragon_lead_ingest \
  --target steam-fronkon \
  --format steam-csv --projection steam \
  --input /absolute/path/games.csv \
  --expected-sha <verified-file-sha256> \
  --tenant <tenant-id> --owner <owner-id> \
  --rights-reference <reviewed-metadata-rights-reference> \
  --acknowledge-metadata-rights
```

From the reported 124,146-game snapshot, the 17-route projection has a gross theoretical 2,110,482 route candidates before deduplication and validation. The actual persisted node count is the only growth-floor receipt. CSV reads AppID/name only; Parquet requires an approved optional pyarrow installation; huge keyed JSON requires optional ijson. Other supported local formats are Modrinth search JSON, game-filtered Wikidata CSV, normalized locator CSV, and normalized NDJSON. Other dataset library entries require reviewed schema-specific normalization or separate structured archive integration. The importer does not auto-download exports, bypass authentication, or ingest full game files.

## Acceptance gates

```sh
python -m pytest backend/tests/test_dragon_lead_graph.py backend/tests/test_dragon_mod_seed_catalogue.py backend/tests/test_dragon_source_directory.py
SKL_DRAGON_LEAD_STRESS=1 python -m pytest backend/tests/test_dragon_lead_graph.py -k tenfold_projection_fixture
```

The optional test generates 153,001 synthetic fixture nodes only for workload qualification. They are never public source seeds. Require independently observed final-head CI, real import receipts reaching 147,020+ distinct persisted nodes, source-specific permission review, real storage pressure/recovery/feed qualification and frontend typecheck/export before declaring production readiness. Live dataset acquisition, permission review, physical capacity, and the actual 147,020-node persisted population remain runtime qualification work. The bundled source identities already exceed the target without synthetic IDs; the tests have been written, not executed in this repository-only development session. The draft must reconcile against the parent catalogue and sibling audiovisual and storage branches. No merge or release.
