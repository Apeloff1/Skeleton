# Recrawl revision revalidation contract (October 2026)

## Purpose

Re-fetching a source cannot justify silently reusing observations, confidence,
citation offsets or knowledge status from an earlier revision. The crawler
needs a bounded way to compare evidence anchored to the previous
`CrawlDocument` with the latest acquired document.

`dragon_crawl_revision.py` implements a deterministic, non-networked
comparison. It uses the same captured-document validation contract defined in
`dragon_crawl_custody.py`. The result is a revalidation *proposal*, not an
acquisition permission, verified truth statement, or new promoted record.

## Processing invariants

1. Verify the previous source inventory and all observed text spans.
2. Verify the complete new source inventory, independently of past evidence.
3. Align sources by declared source identity. Unseen current sources are
   recorded as new; unreturned earlier sources are recorded as missing.
4. Compare content digest, canonical origin, fetched delivery origin,
   MIME/content type, parent sources and declared lineage. Acquiring the
   same content again at a new timestamp does not alone invalidate a passage.
5. Preserve previous evidence receipts immutably. A changed document may
   provide a **candidate** replacement location, but never rewrites the
   earlier citation and never automatically reuses its confidence.
6. Return per-source and per-reading dispositions with a canonical digest,
   suitable for an explicit research-review queue.
7. Block automatic reuse if any observed reading is stale, any source is
   unavailable, new source custody is introduced, or the claim contains no
   prior readings.

## Ambiguous citations

An excerpt is matched against the *new* normalized source text, never against
arbitrary search results. An absent excerpt is invalidated. If the excerpt
occurs exactly once, the comparison proposes that character span for new
semantic review; it is **not** treated as evidence that the claim is still
valid. If an excerpt occurs multiple times, the location is ambiguous and no
automatic candidate is supplied.

Matching is exact and case-sensitive. The bound quotation is a character span
into the extracted Unicode text, not an HTTP byte range. First and second
matches are sufficient to prove absence, uniqueness, or ambiguity; there is
no unbounded occurrence census.

## Safety / anti-inflation

The revision plane inherits the base crawler's fail-closed URL, fetched
content hash, MIME and provenance envelope checks. It also inherits the
captured-source, observation, quotation and relationship budgets.

The comparison does not call search APIs or crawl external destinations.
A missing source is a discrete recorded failure, not a license to fetch an
arbitrary replacement. The same collection of source revisions always yields
the same report regardless of input ordering.

No inference of common publisher independence occurs in this module; for
source independence and promotion, the new set of evidence must separately
pass the attested provenance and strict promotion gates. A healthy revision
comparison is a *prerequisite*, never sufficient proof for promotion.

## Example

```python
from skeleton.ai.webcrawler import compare_crawl_revisions

report = compare_crawl_revisions(
    claim_id="claim-id",
    previous_sources=previous_captures,
    previous_readings=prior_located_readings,
    current_sources=current_captures,
    authorized=True,
)

if not report.prior_readings_reusable:
    # Operator-controlled process: plan new analysis, human review and
    # provenance attestation. Do not restore stale knowledge automatically.
    for observation in report.readings:
        if observation.requires_human_review:
            print(observation.disposition, observation.candidate_span)
```

For an exact-head local regression, run:

```sh
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python -m pytest -q --noconftest \
  tests/test_ai_webcrawler_dragon_crawl_revision.py
```

The preexisting `scripts/check_ai_webcrawler.py` discovers all
`tests/test_ai_webcrawler_*.py`, so the dedicated crawler GitHub workflow
also exercises these tests when CI reaches a runner. Treat queued, skipped,
cancelled, or failed CI as unverified.
