# Empirical evidence requirements for Dragon knowledge

Implemented at the existing `assess_custodied_promotion` boundary. This is a
review-eligibility gate, not permanent-memory authorization or a claim of truth.

## Required evidence

Every sampled source, including opposing observations, must have one current
`EmpiricalCitation` from the authenticated review boundary. It binds the exact
claim ID, source revision, source URL, source-content digest and all cited
evidence locators. Missing or stale review records block eligibility. Incorrect
bindings and malformed records fail before promotion. A trusted evaluation
clock is required; future reviews and expiry at the exact boundary are rejected.

Records require an experiment, benchmark or systematic observation; methods;
measured result; positive sample size; applicability; limitations; raw artifact
URL/digest; study identity; reviewer identity/reference; and a documented
source-quality basis with a citation. Recognized review bases are peer review,
an official technical report or an independent lab. These categories are
review obligations, not automatic endorsements. Popularity, publisher prestige,
confidence scores and repeated readings do not replace empirical measurements.

At least two independent supporting study clusters are required. Shared source
content, custody lineage, ownership, syndication, study identity and artifact
digest can merge sources into one dependency cluster. Two publishers repeating
the same study cannot satisfy the requirement. A verified publisher ownership
registry is mandatory at this boundary, even with a relaxed score policy.
The existing contradiction, reread coverage, calibration and analysis-chain
gates continue to apply. Empirical measurements and empirical calibration are
different requirements; satisfying one does not satisfy the other.

The returned review includes the citations and an empirical-review digest
binding their complete content and evaluation clock. Existing normalized
evidence and manifest digests retain their meanings. No arbitrary numeric
reputation score or automatic neural-weight update is introduced.

## Methodological references

These references inform the review design; they are not evidence for game
mechanics, hardware capabilities or performance results:

1. NIST, AI RMF 1.0, Valid and Reliable: objective evidence must address the
   intended application, with testing and monitoring. The page says a revision
   is in progress; this implementation does not claim certification.
   https://airc.nist.gov/airmf-resources/airmf/3-sec-characteristics/
2. Cochrane Handbook, Chapter 4: multiple reports of the same study must be
   collated rather than counted as separate studies. We adapt that independence
   principle to technical research; this is not a clinical evidence-grading system.
   https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-04
3. ACM, Artifact Review and Badging: artifact availability and independently
   validated results are distinct concepts. The policy was located through
   ACM's indexed primary-source result; direct page retrieval returned 403.
   https://www.acm.org/publications/policies/artifact-review-and-badging-current

References checked 2026-10-10. The two-study minimum is this project's explicit
requirement, not a universal scientific rule or a guarantee of truth.

## Operational and compatibility limits (L00–L13)

- L00–L02: the canonical crawler promotion owner is extended, with no new
  service, database, provider, dependency plane or runtime root.
- L03–L04: external authentication remains required. Legacy calls without
  empirical records or the publisher registry now receive ineligible decisions.
  Callers must supply the new records and clock before resuming promotion.
- L05–L07: the function is read-only. No record is fetched, persisted or signed
  here; the embedding custody boundary must verify artifacts, exact-span
  entailment, reviewer identity and review references. A content hash alone is
  not proof that an artifact exists or its measurements are correct.
- L08–L09: failure reasons identify missing/expired source reviews. Input
  iterables are capped at 10,000 entries before materialization, with bounded
  text, locator and URL fields. Existing assurance capacity limits still apply.
- L10: synthetic fixtures cover distinct evidence, copied studies/data,
  contradictions, source/revision/claim/locator mismatch, missing methods,
  reputation-only assertions, future/expired reviews, duplicate records,
  generator bounds, and digest sensitivity. Fixture results are not real-world
  game-building measurements.
- L11–L12: no schema migration is needed. Rollback should disable promotion
  consumers rather than silently bypass these new requirements. Operators must
  renew expired reviews and obtain missing independent studies; do not fabricate
  metadata to satisfy the gate.
- L13: application-wide Almanakk/Wiki/Hoag rollout, signed review ingestion,
  real-world study curation, applicability reasoning and independently replayed
  experiments remain acceptance work. Normative technical specifications and
  untested design hypotheses must not be relabelled as empirical findings.

Validation: 112 tests passed across provenance promotion, provenance assurance,
publisher registry, knowledge promotion and truth verification. Architecture,
construction, capability interfaces and enterprise-superiority schema checks
passed. Implementation notes retain the existing
`VOL-000.existing_evidence` stale-masterplan failure. Provider bootstrap outcome
is tracked separately and must not be inferred from these tests.

Signed: Codex, 2026-10-10. Scope: this implementation and its listed tests;
no full-volume or enterprise qualification.
