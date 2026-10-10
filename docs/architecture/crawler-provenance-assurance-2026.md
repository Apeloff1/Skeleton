# Crawler provenance assurance and adversarial research (October 2026)

## Status and responsibility

This is a **deterministic research-assurance implementation**, not a new
unrestricted crawler or a claim that an LLM has learned verified facts. It
connects source custody and repeated observations to the existing evidence
distiller and (optionally) the empirical-calibration knowledge promotion gate.

Implementation:

- `dragon_source_independence.py`: existing declared derivation, shared
  lineage, canonical-origin and identical-content dependency closure.
- `dragon_probabilistic_distillation.py`: existing bounded logistic *heuristic*
  score; never an empirically calibrated posterior by default.
- `dragon_provenance_assurance.py`: custody-checking adapter, conservative
  merges, leave-one-cluster-out counterfactuals, reviews and research actions.
- `dragon_provenance_promotion.py`: strict adapter to the existing promotion
  decision system (calibration and human-chain requirements stay in place).
- `tests/test_ai_webcrawler_dragon_provenance_*.py`: adversarial regression
  suite run by the repository's exact-head crawler workflow.

## Trust boundary and failure modes

The acquisition plane remains responsible for DNS/IP pinning, robots
permission, publisher licensing, crawl budgets, response limits and redirect
checks. This analysis module **performs no HTTP I/O**. Its authorization
parameter guards a caller boundary, but it cannot authenticate that caller.
A production caller must load provenance only from a trusted ingestion receipt,
including the immutable content hash of the sampled source.

Each source has a unique `source_id`, content digest, canonical HTTP(S) URL,
optional source parents and lineage tokens. Claim readings reference that ID.
Unknown/malformed sources, duplicate identities, illegal URLs, undeclared
parents, oversized manifests, cross-claim observations, nonfinite confidence
and repeated pass IDs fail closed.

Canonical-origin, content-identity, parent-derivation and lineage matches join
sources into one dependency cluster. **Caller-supplied independence labels can
only further merge clusters.** Even if a mirror claims a new independence label,
a shared content hash or ancestry prevents its readings from becoming new
independent corroboration. Ghost parent nodes may preserve the dependency
chain but cannot contribute votes without actual readings.

Publisher attestations strengthen the conservative closure. If the caller
provides the existing `ProvenanceRegistry`, the assurance plane also joins
all sources sharing the **same verified ownership** or **same syndication
network**, even when each URL and content hash differs. These are two
independent merger criteria: separate feeds owned by the same publisher are
not artificially separated. The optional
`AssurancePolicy(require_attestations=True)` fails closed unless a registry
with strict attestation policy is supplied and every manifest source resolves.
The registry's fingerprint is included in the analysis fingerprint, so a
custody-attestation update invalidates old assurance conclusions.

An honest statement of statistical independence often requires more evidence
than the manifest can prove. A distinct cluster is only a *conservative
candidate for independence*, never proof that two publications did not
coordinate off-platform. Without a trusted manifest, the strict promotion
adapter refuses the operation.

## Analysis contract

`assure_crawler_evidence(claim_id, readings, provenance, authorized=True)`
returns a stable, immutable report containing:

1. The existing `Belief` computed using custody-derived groups, with
   `heuristic_logistic_score` probability semantics.
2. Source-cluster membership, content digests and detected dependency reasons.
3. A counterfactual belief after removing *each* sampled source cluster,
   including whether the support majority reverses.
4. Minimum held-out support, insufficient reread coverage, disagreement,
   fragile single-source dependence and weak heuristic support.
5. Budgeted, deterministic next research actions. These are plans and do
   not fetch, execute models, collect screen recordings or promote memory.
6. A canonical report fingerprint binding claim, evidence, policy, custody,
   cluster membership and holdout calculations.

Confidence from ten readings of one page cannot become ten independent
corroborators. Three reread lenses per source is the current default research
coverage, but this controls *review completeness*, not statistical independence.
The default research candidate gate requires two distinct source clusters,
sufficient reading coverage and robust heuristic support after excluding each
cluster. Every report still requires human review.

The conservative action planner favors genuinely new primary sources over
more readings of the same source when independence is deficient. In conflict
cases it schedules targeted falsification and locator-level investigation.
All action lists have explicit bounded capacity and deterministic ordering.

## Knowledge promotion bridge

New integrations should call `assess_custodied_promotion` instead of directly
passing unverified `EvidencePass.independence_group` labels into the legacy
`assess_promotion` function.

The bridge:

1. Validates the entire custody manifest and all sampled readings.
2. Replaces all caller-labelled groups with conservative custody-cluster IDs.
3. Runs the original knowledge promotion gate on the *same normalized evidence*.
4. Checks its evidence digest against the assurance report.
5. Carries forward every provenance-assurance blocker and never upgrades a
   rejected promotion into an eligible one.
6. Retains the original policy's empirical calibration, quality receipt chain,
   adversarial influence and human approval requirements.

The legacy entry point remains intact for compatibility. Consumers that
require custody integrity must use the strict bridge; the presence of this
adapter alone does **not** migrate existing callers. For systems demanding
stronger publisher controls, pass
`AssurancePolicy(require_attestations=True)` and an authorized
`ProvenanceRegistry` into the bridge. A missing or unknown publisher cannot
silently qualify as an independent research source.

## Resource constraints and auditability

- At most `EvidencePolicy.max_evidence` readings.
- At most `AssurancePolicy.maximum_sources` provenance sources.
- At most `AssurancePolicy.maximum_holdout_groups` leave-one-out comparisons;
  excess is an error, not a misleading partial robustness certificate.
- At most `AssurancePolicy.maximum_actions` proposed next actions.
- At most twelve named reread lenses in the current scheduler. A policy with
  a larger minimum emits an explicit lens-extension task rather than crashing
  or silently pretending a completed analysis.

The first implementation uses exact leave-one-group-out recomputation. For
very large research corpora, batch claims or introduce a verified, equivalent
incremental-scoring primitive before lifting the comparison budget.

## Reproduction

```sh
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  python -m pytest -q --noconftest \
  tests/test_ai_webcrawler_dragon_provenance_assurance.py \
  tests/test_ai_webcrawler_dragon_provenance_promotion.py

python scripts/check_ai_webcrawler.py
```

Both tests and the repository exact-head workflow must pass before merging.
The workflow's checkout SHA must equal the PR head; skipped or cancelled jobs
are not proof of success. Deployment must separately verify authority,
provenance custody signatures, provider permissions and model-calibration
artifacts, none of which this module manufactures.


## Captured-document custody (strict entry point)

`dragon_crawl_custody.py` adds the missing connection from the existing
`CrawlDocument` acquisition contract to evidence records. The caller supplies
real acquired `CrawlDocument` values through `CapturedSource` wrappers and
`LocatedReading` span descriptors. Unlike free-form notes, each observation
must be an exact, nonblank character range in the captured normalized text.

The binder rejects mismatching SHA-256 content digest, acquisition-receipt URL,
digest, timestamp or response status, unsafe canonical/fetched URLs, oversized
document text, unsupported content type, duplicate identity, undeclared
derivation parents, out-of-bounds quotations, and nonfinite evidence scores.

`LocatedReading` contains an analyst's claim polarity and confidence. These
remain unverified interpretations, even though the quotation locator itself
is content-addressed. The binder never infers that a statement is true simply
because the text contains it.

```python
from skeleton.ai.webcrawler import (
    CapturedSource, LocatedReading, assure_captured_crawl,
)

# `document` must be a CrawlDocument obtained by the trusted crawler path.
review = assure_captured_crawl(
    "claim-id",
    (CapturedSource("source-id", document),),
    (LocatedReading("source-id", "pass-1", "claim-id",
                    True, 0.7, 0.8, 100, 148),),
    authorized=True,
)
# Review is a research proposal, not approved knowledge.
assert not review.assurance.promotion_authorized
```

Callers seeking promotion must carry `review.custody.evidence` and
`review.custody.sources` into `assess_custodied_promotion`, with a trusted
attestation registry where required. The acquisition boundary must retain
authoritative capture receipts and licenses; a SHA-256 digest alone does not
prove when or by whom a page was retrieved.

For testing, the acquired document text is canonically normalized by the
existing crawler extraction code before span offsets are chosen. The binder
does not silently trim or rewrite quoted offsets; downstream consumers can
therefore reproduce the exact evidence slice.

## Non-goals and unresolved integration work

- Existing call sites using legacy promotion directly are not automatically
  migrated to the strict captured-source path.
- The submitted provenance inventory has structural validation, not a
  transport-level signature. Authenticated ingestion custody is a separate
  deployment prerequisite.
- A quoted passage proves the passage occurred in the captured text, not
  that the real-world claim is true. Causal and human review remain mandatory
  where configured.
- Robots permission, source licensing, authenticated publisher identity,
  recording consent and retention policy are enforced by their upstream
  respective planes rather than fabricated by this reporting module.
- Source revisions must be captured and retained as immutable documents for
  external replay. The local binder does not persist document bytes.
