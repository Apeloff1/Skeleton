# Dragon source-expansion admission — October 12, 2026

## Result and scope

The immutable eight-catalog baseline contains **4,405 distinct unreviewed candidate URLs**. Supplements 0020–0022 contain **463 + 223 + 278 = 964** additional raw hyperlink identities, bringing the recorded *raw-link* inventory to **5,369 / 44,050 (12.19%)** of the requested tenfold target. The distinct canonical URL inventory is smaller, because some recorded links differ only by fragments or trailing slashes and some may overlap the original 4,405. These numbers are link discoveries, **not** individually verified sources, approved knowledge, legal-use grants, downloaded media, embeddings, model weights, or training examples.

Before this change, all 964 were provisional evidence files outside the canonical SQLite almanac queue. A follow-up adversarial review identified **46 raw URLs that normalize differently** and **five cross-supplement canonical collisions**. Raw source IDs and receipts must remain intact as provenance, while canonical destinations receive only one policy job. The new `dragon_discovery_admission.py` bridge and `dragon_almanac_cli import-supplements` command reconcile these into distinct pending **policy** jobs and source-almanac memberships, preserving all 964 original discovery receipts. The importer performs no network access. Importing the bridge into the branch does **not** itself ingest the data into any running service; a trusted operator must run the command against the approved database.

## Runbook (trusted operator, at the repository root)

```bash
python -m skeleton.ai.game_builder.dragon_almanac_cli bootstrap \
  --trusted-local-operator --owner OWNER --database /path/to/owner-library.sqlite

python -m skeleton.ai.game_builder.dragon_almanac_cli import-supplements \
  --trusted-local-operator --owner OWNER --database /path/to/owner-library.sqlite \
  --supplement docs/ai/evidence/dragon-source-expansion-20261011-batch-0020.json \
  --supplement docs/ai/evidence/dragon-source-expansion-20261012-batch-0021.json \
  --supplement docs/ai/evidence/dragon-source-expansion-20261012-batch-0022.json
```

If the trusted operator has already bootstrapped the baseline, only the second invocation is needed. The importer refuses a missing, out-of-order, duplicated, or count-divergent chain. It verifies the baseline catalog digest and unique URL identity and requires consistent unapproved states. Git repository/blob identities and catalog line numbers are retained **as source-discovery claims**, not described as authenticated signed provenance. Canonical URLs are allocated metadata-only records with no rights or training grant; each original raw source ID remains independently documented as a discovery receipt and maps to the normalized source-ID digest. All DB writes, topic membership and new policy-stage work occur in one transaction, with idempotent replay and owner isolation.

`status` can inspect the owner-scoped queue. A worker can acquire a source only through its existing authenticated and bounded claim path. Its subsequent policy stage requires current robots, terms, SSRF and use authorization; a successful fetch and the source rights/Wiki/HOAG review require separate evidence. No supplement bypasses existing enforcement or automatically grants access.

## Next substantive work

Move from candidate quantity to lawful, reproducible acquisition: deploy the owner-bound import from an authorized operator; triage provisional sources by primary documentation, platform/era, originality and game-building utility; capture permission and exact target revisions; obtain independently reviewed narrow claims and replayable experiments; then promote measured knowledge only through the existing Wiki/HOAG/right-to-use gates. Expand beyond the current eight original source catalogs toward diverse official standards, hardware manuals, accessible homebrew SDK docs, historical specifications, video metadata and research repositories, with independently bounded connector/robots policy for every host. Explicitly distinguish public documentation, licenses for code or assets, and training rights.

## Limitations

- No new network fetch, independent source validation, source-material license or training authorization is claimed.
- The 964 records are *available for queue import*; durable admission requires running the CLI against the deployment database.
- No automated legal conclusion, model fitting, weight promotion, original game shipping or exhaustive archive has occurred from this batch.
- CI on the exact GitHub commit and operator provisioning are separate release gates.

Code: `skeleton/ai/game_builder/dragon_discovery_admission.py`.
Regression: `tests/test_dragon_discovery_admission.py`.

## Next reproducible extraction lane: nine pinned catalogs

The manifest `machine/dragon_pinned_crawl_catalogs_20261012.json` now lists nine **additional, Git-revision-identified catalog candidates**: Game Boy, Nintendo 64, CHIP-8, C++ game creation, console-emulator documentation and case studies. This is nine potential **discovery catalogs**, **not** nine approved crawler sources and **not** yet a verified increment to the 5,369 distinct URLs.

A source operator who has separately established permission to retrieve the catalog text can save each exact commit-pinned `README.md` to `/approved/catalog-cache/<owner>/<repo>/README.md`. The `dragon_catalog_expansion` utility does **not** access the network. It rejects modified content by recomputing the Git blob SHA-1 before extracting source links and header/line lineage. It then deduplicates against the full 4,405-entry baseline and the three existing supplements using the canonical URL parser, emits a fourth unapproved supplement, and checks the cumulative 10× target math before writing the evidence file. SHA-256 of each extracted README is also included to support stronger subsequent custody.

Example, after populating the policy-approved cache with the **exact** pinned text:

```bash
python -m skeleton.ai.game_builder.dragon_catalog_expansion \
  --trusted-local-operator \
  --cache /approved/catalog-cache \
  --observed-at 2026-10-12T02:26:00Z \
  --supplement docs/ai/evidence/dragon-source-expansion-20261011-batch-0020.json \
  --supplement docs/ai/evidence/dragon-source-expansion-20261012-batch-0021.json \
  --supplement docs/ai/evidence/dragon-source-expansion-20261012-batch-0022.json \
  --output docs/ai/evidence/dragon-source-expansion-20261012-batch-0023.json
```

Pass the generated fourth supplement along with the first three, in that order, to `dragon_almanac_cli import-supplements` to create the additional **pending policy-stage jobs**. The timestamp above illustrates argument shape; operators must use the actual evidence-backed retrieval timestamp and never silently present an example as an observation.

The new acceptance suites `tests/test_dragon_discovery_admission.py` and `tests/test_dragon_catalog_expansion.py` are wired into the hosted Dragon AI Verification workflow. They test full previous-chain counts, idempotency and tenant isolation, atomic corruption rejection, pinned-blob mismatch and non-promotability of unapproved source metadata. Hosted results must be inspected at exact PR head before release.

## Per-header source almanacs and canonical deduplication

An observed catalog hierarchy is now preserved as its own indexed almanac lineage. For example, an independently retrieved catalog item with the observed headings `Games → Controls → Input Latency` receives membership in each ancestor of `Sources → Provisional → <catalog repository> → Games → Controls → Input Latency`. Only **observed** headings are projected; the repository-only fallback for origin formats without heading data is explicit and does not invent new taxonomy.

Metadata for an original raw URL, including every quoted heading path and repository/README identity, is retained in the owner-scoped `dragon_almanac_supplement_receipts_v2` table. Acquisition jobs use the independently canonicalized URL and its derived source ID. This prevents five known fragment/hostname collisions from creating duplicate policy jobs, while retaining all 964 raw discovery receipts. The canonical unique count is computed against the full baseline at import time; the previously recorded total **5,369 is a raw discovery count**, not a validated canonical count.

Operators should first run the single-source import in a staged tenant and inspect `new_discovery_sources`, `new_provenance_receipts`, `new_policy_stage_jobs`, `raw_provisional_urls` and `canonical_discovered_urls`. Only the policy stage can authorize subsequent fetching; all derivative knowledge remains unreviewed until the independent review, rights and Wiki/HOAG gates have run. No source topic membership is itself evidence of factual accuracy.

## Bounded metadata inspection

A trusted local operator can inspect the owner-scoped source hierarchy without fetching any source or promoting extracted text:

```sh
python -m skeleton.ai.game_builder.dragon_almanac_cli discovery-topics --database dragon.sqlite --owner studio --trusted-local-operator
python -m skeleton.ai.game_builder.dragon_almanac_cli discovery-topics --database dragon.sqlite --owner studio --parent topic-<exact-topic-digest> --limit 25 --offset 0 --trusted-local-operator
python -m skeleton.ai.game_builder.dragon_almanac_cli discovery-sources --database dragon.sqlite --owner studio --topic topic-<exact-topic-digest> --limit 25 --trusted-local-operator
python -m skeleton.ai.game_builder.dragon_almanac_cli discovery-receipts --database dragon.sqlite --owner studio --source source-<exact-source-digest> --limit 25 --trusted-local-operator
```

`discovery-topics` returns the direct children of an observed heading path, with inherited source counts. `discovery-sources` returns one canonical acquisition identity per URL, its existing policy-stage job state and the total count of unreviewed raw provenance receipts. `discovery-receipts` returns the exact original link, catalog evidence path, observed heading paths, pinned identifiers and receipt digest. Each view validates stored source or evidence digests before presentation and carries explicit `training_authorized: false` and `scope: discovery_metadata_only` fields. Pagination is bounded to 100 rows and all queries require an explicit owner. The CLI is a local operator interface, **not** an HTTP endpoint and **not** a new runtime permission.

## Four-batch raw discovery and mission-directed source scouting

The discovered evidence chain now contains four consecutive supplements. The first three retain their original `partial_discovery_only_not_ingested_into_canonical_queue` status and the fourth records `raw_discovery_only_not_ingested_into_canonical_queue`. Both are explicitly **non-authorizing** states; neither can mark a URL fetched, independent, rights-cleared or training-approved. The import bridge validates both historical and current count-field conventions before making any database writes.

A trusted local operator can feed all four supplements, in exact sequence, into an isolated SQLite library:

```sh
python -m skeleton.ai.game_builder.dragon_almanac_cli import-supplements \
  --database dragon.sqlite --owner studio --trusted-local-operator \
  --supplement docs/ai/evidence/dragon-source-expansion-20261011-batch-0020.json \
  --supplement docs/ai/evidence/dragon-source-expansion-20261012-batch-0021.json \
  --supplement docs/ai/evidence/dragon-source-expansion-20261012-batch-0022.json \
  --supplement docs/ai/evidence/dragon-source-expansion-20261012-batch-0023.json
```

The owner-scoped `mission-scout` command ranks **unreviewed discovery metadata**, allowing the next human or policy worker to focus on a specific console, genre, era, mechanics editor or port target. For example:

```sh
python -m skeleton.ai.game_builder.dragon_almanac_cli mission-scout \
  --database dragon.sqlite --owner studio --trusted-local-operator \
  --query "gameboy homebrew input collision physics" \
  --platform "Game Boy" --genre "platformer" --era "1990s" \
  --limit 25 --scan-budget 4000
```

This is an explainable, deterministic **proposal**. It scores intersections between goal terms and URL paths, observed catalog headings and repository names, then displays host-diverse candidates. It does not claim different hosts are independent originals; it never treats a ROM, BIOS, dump or download link as automatically lawful; it **never** starts the durable policy queue or fetches media. Rights-risk indicators require manual review. `scan_truncated` and unmatched terms disclose when the bounded metadata scan cannot cover the entire source corpus.

Progress denominators are not interchangeable: **5,438** records are raw URL leads toward the **44,050** raw target (12.35%), whereas **736 / 4,405** represents sequential first-pass acquisitions of the original registry. Neither measure demonstrates 5,438 usable or independent sources. Canonical deduplicated totals are computed at ingestion, and all discoveries remain unapproved for training.
