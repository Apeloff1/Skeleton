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


## Durable revision journal and restart recovery

`dragon_revision_journal.py` provides an owner-scoped SQLite hash chain for
review dispositions. It is an *audit record* and does not authorize ingestion
or autonomous knowledge promotion.

A journal entry carries the previous and current custody fingerprints,
canonical revision-report fingerprint, whether previous observations remain
reusable, invalidation count, source additions/removals, caller-provided
observation time, and the previous event's hash. The journal is deliberately
independent of wall-clock calls and network requests.

A write requires an explicit `authorized=True` boundary and the expected
sequence number. `BEGIN IMMEDIATE` fences writers; a mismatched sequence,
changed report, modified chain head, or a backwards timestamp fails closed.
Retransmitting an *identical* successful write with the original sequence and
observation time returns its existing receipt instead of appending twice.

Before accepting a review, the journal recomputes the revision report's
canonical fingerprint, binding all source and reading dispositions, span
positions, candidate locations, missing/new source sets, invalidation count,
and claim-reuse outcome. A syntactically valid but stale SHA-256 digest is
insufficient.

```python
import sqlite3
from skeleton.ai.webcrawler import RevisionJournal, compare_crawl_revisions

journal = RevisionJournal(sqlite3.connect("crawler_revision.sqlite3"))
review = compare_crawl_revisions(
    "claim-id", previous_captures, previous_located_readings,
    new_captures, authorized=True,
)
latest = journal.latest("owner-id", "claim-id", authorized=True)
receipt = journal.append(
    "owner-id", review, observed_at=some_external_timestamp,
    expected_sequence=latest.sequence if latest else 0,
    authorized=True,
)
if not journal.verify("owner-id", "claim-id", authorized=True):
    raise RuntimeError("review history integrity check failed")
```

The caller must pass a stable owner identity and a trusted observation time.
The journal refuses writes inside an existing caller transaction, to avoid
interfering with its rollback semantics. `max_per_claim`, read limits, and
verification limits bound resource use. Owner-scoped `erase` deletes that
owner's event rows and head pointers without touching other owners.

The hash chain detects modification and accidental divergence *while its
trusted head remains available*. It does not authenticate the database host,
provide an externally anchored signature, or prevent a privileged database
operator from rewriting the full chain and its head. Production deployments
must externally custody or sign periodic head hashes to resist that threat.

Crawl-acquisition fingerprints now include delivery URL, content type,
acquisition metadata, source quality score, and capture time in addition to
the source-text digest. A timestamp-only re-fetch therefore receives a new
**capture audit identity** while the textual revision-review logic may still
find the old anchored quotation reusable. This is intentional: acquisition
identity is not equivalent to semantic evidence continuity.

The overall review cannot be declared reusable if *any source inventory
member* changed, including unobserved parents and dependency sources that
could influence the independence model. New evidence still goes through the
separate provenance-attested and calibrated promotion gates.


## Quality and policy drift without textual revision

A textual hash is not sufficient to certify that a source is epistemically
unchanged. The revision comparator now distinguishes `QUALITY_CHANGED` from
`DELIVERY_CHANGED`, `LINEAGE_CHANGED`, or a content revision. A changed
source-quality score or changed acquisition policy metadata (including status
and additional attested fields) requires a renewed assessment even when the
old quoted text remains byte-for-byte identical.

The normalized acquisition metadata comparison excludes **only**
`fetched_at`: a timestamp-only recrawl does not by itself change the factual
meaning of a cited quote. The complete capture receipt nevertheless changes
its custody hash, allowing an auditor to distinguish separate acquisitions.

Promotion consumers must not interpret a non-invalidated quotation span as a
blanket claim-approval token. An observed claim is reusable only if every
source in the dependency inventory remains unchanged, all its cited readings
still match the same source and custody semantics, and downstream assurance
and promotion policy separately approve the candidate.

The dedicated regression suite covers changed score, status, metadata,
internal destinations, boolean-typed metadata, omitted source parents,
ambiguous citation moves, forged review digests, stale journal sequences and
head tampering. These are committed tests; they do not count as passed until
the repository's exact-head CI runner reports success.
