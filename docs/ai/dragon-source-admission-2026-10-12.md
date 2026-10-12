# Dragon source-expansion admission — October 12, 2026

## Result and scope

The immutable eight-catalog baseline contains **4,405 distinct unreviewed candidate URLs**. Supplements 0020–0022 contain **463 + 223 + 278 = 964** additional distinct URLs, bringing the *discoverable* inventory to **5,369 / 44,050 (12.19%)** of the requested tenfold target. These numbers are link discoveries, **not** individually verified sources, approved knowledge, legal-use grants, downloaded media, embeddings, model weights, or training examples.

Before this change, all 964 were provisional evidence files outside the canonical SQLite almanac queue. The new `dragon_discovery_admission.py` bridge and `dragon_almanac_cli import-supplements` command import these only as pending **policy** jobs and source-almanac memberships. The importer performs no network access. Importing the bridge into the branch does **not** itself ingest the data into any running service; a trusted operator must run the command against the approved database.

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

If the trusted operator has already bootstrapped the baseline, only the second invocation is needed. The importer refuses a missing, out-of-order, duplicated, or count-divergent chain. It verifies the baseline catalog digest and unique URL identity and requires consistent unapproved states. Git repository/blob identities and catalog line numbers are retained **as source-discovery claims**, not described as authenticated signed provenance. Distinct URLs are allocated metadata-only records with no rights or training grant; the source owns its URL and source-ID digest. All DB writes, topic membership and new policy-stage work occur in one transaction, with idempotent replay and owner isolation.

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
