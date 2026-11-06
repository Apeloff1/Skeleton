# Dragon crawler campaign stack: operating and integration contract

The Dragon campaign stack is an additive research and inspection capability within
the canonical `skeleton/ai/webcrawler` owner. It is deterministic and transport-free.
The existing `operations.CrawlRun`, its bounded `run_slice`, and CORE_DB Mongo
snapshots remain authoritative. These modules do not start an autonomous crawler,
scheduler, provider, model, database or parallel storage authority.

## Production surfaces

| Layer | Purpose | Refusal condition |
| --- | --- | --- |
| contracts | Tenant/owner/consent/request fingerprint, purpose and host allowlist | Mismatch, expired consent, invalid identity |
| budget | Requests, source/documents, measured bytes and reserved unknown outcomes | Any overgrant, exhausted capacity, pending dispatch |
| planner | Bounded expected-information-gain ranks and host-fair dispatch hints | Noncanonical URL, wrong host, depth/cap violation |
| evidence | Retained-text hashes, anchored passages, instruction risk, source quality | Tampering, wrong consent, unreviewable text |
| lineage | Typed provenance DAG, same-content families, withdrawal closure | Cycles, dangling or duplicate identity |
| revisions | Source change/withdrawal and citation revalidation | Changed, absent or unreviewable evidence |
| journal | Bounded hash-chained portable event/CAS inspection artifact | Replay, stale revision, tamper |
| integration | Rehydrate and verify whole canonical CrawlRun snapshot | Any snapshot/source/authority mismatch |
| diagnostics | Utilization, rejection, truncation and review-pressure counters | Unknown values or fabricated estimates |
| recovery | Physical worker join and canonical checkpoint custody preflight | Unconfirmed worker or Mongo commit |
| control | Plan, pause, resume, cancel proposals against exact sequence | Stale source, wrong authority, unsafe transition |
| references | Recheck exact citation hashes, Unicode offsets and current retained text | Missing, stale, partial, withdrawn or injection-held capture |
| recrawl_advisory | Adaptive source reread proposals from trusted volatility observations | Out-of-consent future read and unretained source IDs |
| stopping | Explicit plateau and budget stop with unreviewed evidence escalation | Never auto-promotes a claim or assumes host independence |

## Authorized usage

An application operator supplies a real `CrawlRequest`, exact immutable
`CampaignScope` (tenant, owner, consent, allowed hosts, expiry, purpose),
current application authorization and a verified canonical persisted crawl
snapshot to `inspect_crawl_campaign`. The adapter invokes
`CrawlRun.from_snapshot` before producing a bounded plan. Candidate hints
cannot insert URLs that were not already committed in the crawler frontier.

Do not accept client-supplied booleans as evidence of current authorization:
the backend must independently enforce session role, tenant scope, consent
expiry, worker lease and Mongo optimistic version before any durable mutation.
A plan is an advisory hint, not a dispatch authorization or pre-I/O reserve.
The canonical runner still enforces robots, DNS, redirect, public destination
policy and conservative reservation before attempting HTTP.

Retained source passages remain explicitly **unreviewed external evidence**;
successful hash checks do not establish source truth, rights, training consent
or knowledge promotion. Truncated sources cannot be certified as having
their entire original content rehashed. All observed prompt-injection cues
are held for human review. A revision or withdrawal invalidates dependent
citations, rather than silently reusing stale passages.

## Validation, failure recovery and rollback

Run the focused suite after delivery:
`python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_campaign_stack.py' -v`

Then run the canonical architecture, construction, interface and enterprise
validators listed in root `AGENTS.md`, followed by the wider crawler tests
and exact-head CI. No claim of live endpoint integration, Windows/WSL2,
real public acquisition, device load or production launch qualification is
made by this additive code. Any integration must retain existing pre-I/O
checkpoint semantics; unknown transport outcomes keep their reserved budget.

Rollback is to stop consuming the additive inspection adapter or revert
the feature commit. No database migration, new service, durable authority,
model provider dependency or additional network endpoint was introduced.

Reference revalidation and adaptive recrawl planning are also offline, advisory
operations. A due date outside the current consent window requires a newly
approved capture; a citation hash match is only eligibility for human review.

IMPORTANT: Before returning evidence, the caller must obtain the currently
withdrawn/stale source identifiers from the authoritative Mongo source-use
policy, pass them as `revoked_source_ids`, and recheck policy at the real
publication boundary. Withdrawn source text is excluded from campaign evidence
rather than returned with a warning. The stand-alone inspection API cannot
infer later per-source policy changes from an old crawl snapshot.

## Deep research and temporal wave

The extended, explicitly typed workbench also implements:

- **Operator-defined objectives**: purpose, domain, evidence thresholds, required
  and blocked lexical terms, stable objectives and bounded planning budget.
- **Claim-evidence matrix**: attributed statements, opposing evidence stances,
  source-revalidation receipts and independently reviewed source groups.
  Review and factual truth remain separate; no triage score is a probability
  of truth or a legal rights determination.
- **Coverage and discovery**: anchored evidence deficits mapped to the current
  frontier, host fairness, duplicate/near-duplicate source families and
  conservative value-of-information heuristics. The plan cannot invent URLs.
- **Temporal custody**: bounded Unicode-preserving exact revision spans,
  source-version identity validation, partial-retention holds and deterministic
  recrawl review proposals.
- **Ephemeral lexical research**: an owner-bound, in-memory, limited passage
  index rebuilt from currently authorized canonical Mongo captures.
  It is not a new persistence authority or a verified knowledge database.
- **Operational assurance**: robots state and cooldown diagnostics, snapshot
  event-risk inventory, resource-pressure advice and explicit incident holds.
- **Contradictions and export**: source-dependency clusters, opposing attributed
  readings, review packets, replay chains and cross-receipt source identity.
  Hashes are integrity checks, never cryptographic authorizations.
- **Composition**: \`compose_dragon_workbench\` builds one immutable, source-fenced
  inspection linking all these receipts to the same run/source snapshot.

### Authenticated read-only product surface

Two additive routes are exposed under the existing Dragon Academy router:

- \`GET /api/dragon-academy/crawler/sessions/{session_id}/research/inspection\`
  gives budget and host breakdown, retained source metadata, risk diagnostics,
  and stop/review posture without raw source text.
- \`GET /api/dragon-academy/crawler/sessions/{session_id}/research/search\`
  rebuilds and searches the current retained passage index, with bounded
  \`query\`, \`mode\` and \`limit\`.

Both reuse the existing authenticated \`_crawler_scope\`, canonical
\`DragonCrawlerApplication._owned\`, source-policy freshness, withdrawals,
and complete CrawlRun snapshot revalidation. No new creation, mutation,
provider, worker, storage, or public access endpoint is added. Both surfaces
must be checked with backend auth and Mongo integration tests before launch.

### Exact-head source suite

\`python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_campaign_depth.py' -v\`
must pass alongside the original focused suite. Backend source files are
compiled in the same workflow. This does not replace live Mongo/API auth,
real transport, performance, install or release qualification.



## Dragon Atlas: source-policy-first operational research (additional workload)

The Atlas is a bounded, synchronous extension of the existing canonical
CrawlRun snapshot owner, not an alternative fetcher or database. Core entry
point: skeleton.ai.webcrawler.dragon_campaign_stack.compose_dragon_atlas.
It requires a caller-authenticated current policy decision for *every*
captured source before any retained page text is ranked or serialized.

### Ten strictly ordered stages

1. Authenticated, exact-source policy projection: explicit consent, purpose,
   policy revision, source content hash, effective/expiry window, complete
   retained-source universe. Missing and expired policy decisions fail closed
   or exclude sources. Rights, publishing and training remain separately held.
2. Canonical workbench: budget, risk, robots, goals, claim matrix, lineage,
   source revalidation, review packet and mission stop controls.
3. Operator-objective query lattice: finite, deterministic, bounded lexical
   variants, each traceable to an operator objective. Never expand the URL
   allowlist or accept model/page-generated research instructions as authority.
4. Ephemeral source index: exact Unicode span/text/hash revalidation from a
   fully validated canonical CrawlRun snapshot.
5. Multiple-query, rank-fused retrieval: bounded reciprocal-rank aggregation,
   objective IDs, per-source and per-host caps, current withdrawal enforcement
   on every constituent search, no external embeddings or provider calls.
6. Research context envelope: strict source-content hash/span/withdrawal checks,
   JSON data encapsulation, byte/character/reference caps and explicit
   untrusted-data status. The consumer must separately maintain a safe prompt
   boundary, request fresh policy and never obey page instructions.
7. Independence counter-audit: operator-supplied provenance groups are
   collapsed when exact copies, revisions or derived lineage could inflate
   corroboration. No conclusion is auto-verified.
8. Canonical-frontier allocator: advisory host-fair dispatch slots based only
   on the immutable current frontier, conservative capacity and independently
   observed resource pressure. Without measured telemetry the planner returns
   zero slots; backend CAS, robots, DNS, consent and physical-worker fences
   remain mandatory.
9. Review scorecard: source eligibility, objective coverage, unreviewed claims,
   evidence references, independent group deficits and immutable hard holds.
   Scores are diagnostic triage quantities, not probabilities or certification.
10. Optional cross-checkpoint drift: same-run sequence checks, revision and
    withdrawal invalidation without falsely inferring remote content freshness.

Every stage is linked to a previous-stage SHA-256 receipt. This is
tamper-evident deterministic bookkeeping, **not authentication**. Atlas
trace verification checks exact-run/snapshot/stage identities and rejects
authority escalation, but it cannot authenticate operator-supplied source
policy or replace backend admission and human review.

### Backend integration contract

Retrieve the tenant/owner-bound CrawlRun and its complete current source
policy under the existing authenticated backend route. Mark
policy_snapshot_authenticated true only *after* that authority has been
verified by the application; model-generated or caller-provided booleans
without an authenticated boundary are not a valid integration. Run Atlas
synchronously on this read-only snapshot, do not store or publish the
context envelope as knowledge, and recheck policy before any downstream
consumer reads it. No new network service, new policy grant, database
migration, autonomous worker or source use permission is introduced.

### Regression qualification

python -m unittest discover -s tests -p 'test_ai_webcrawler_dragon_atlas.py' -v

The exact-head Dragon source workflow additionally compiles all Atlas
modules, then runs existing campaign tests and Atlas tests. It is only one
source qualification boundary. Root AGENTS.md rules, wider backend and
security checks, live-device E2E, authorization route tests, packaging and
release approval are separate mandatory gates. This branch remains a
draft until those gates are independently satisfied.


### Authenticated Dragon Atlas application endpoint (read-only)

POST /api/dragon-academy/crawler/sessions/{session_id}/research/atlas

Body: {"objectives": [{"objective_id": "archive-method",
"question": "How was archive capture methodology documented?",
"dimension": "method", "stage": "verification", "priority": 0.9,
"minimum_reviewable_passages": 1, "minimum_attested_groups": 1,
"max_source_age_seconds": 3600,
"required_terms": ["archive", "capture"], "blocked_terms": []}]}

The existing authentication dependency derives tenant/owner; no request field
can claim an owner, consent revision or policy authorization. The backend
reads and replays the Mongo-held run, projects every retained source against
its existing source-use, capture-age and consent authority, constructs the
strict policy decision universe and composes the Atlas. It performs another
authenticated session/source-policy read before responding and aborts on any
revision change. The returned dashboard contains stage hashes, query counts,
source IDs and exact passage anchors, bounded diagnostic scores, review holds
and zero dispatch authority. **No retained page body or research envelope
JSON is returned.** A later consuming operation must re-check policy and
source revision again; the dashboard is not a durable approval receipt.

This POST is a read-only analytical query (operator-provided objectives),
not a capture command. Its Pydantic input denies extraneous fields,
bounds all strings and list sizes and cannot grant external networking.


### Current source-policy impact and transitive independence

policy_invalidation.assess_policy_invalidation() compares two bounded
policy projections for the same crawl snapshot. Any source-use state
or policy-revision transition invalidates its dependent source lineage,
claim evidence, fused retrieval references and serialized context. A policy
revision is never silently reused. The report produces exact source/claim/
objective invalidation identities, but only the canonical application
mutates actual policy and a later consumer must re-fetch current access.
Cross-checkpoint source differences belong to source_drift.py.

independence_audit.audit_independence() additionally closes the complete
acyclic derived_from / revision_of graph. Two provenance groups
sharing an upstream source are both held until a person reviews their
true independence, including when their connection passes through an
intermediary not represented in either asserted group.

### Operator-labeled retrieval comparator

retrieval_benchmark.evaluate_fused_retrieval() computes bounded recall@k,
MRR@k, and normalized DCG@k from explicit operator-reviewed graded
passage labels. A judgment must reference an exact current indexed
source/span/hash and operator objective. Missing labels produce null,
not invented performance zeros. No result is a factual confidence score.

retrieval_benchmark.compare_retrieval_benchmarks() allows only comparisons
sharing mandate, crawl snapshot, source index, objective definitions,
relevance-label universe and k; otherwise it fails closed. These
metrics are diagnostic offline source ranking, not a claim of global
SOTA, production native evaluation, scientific ground truth, or
release certification.


## Operational review and Jeeves handoff: 16-stage Atlas

The existing Atlas now composes six additional operational stages, all
read-only and bounded by the same canonical Mongo crawl snapshot:

11. A policy-bound typed evidence graph of source identities, exact passage
    spans, authored objectives and review-held claims, including provenance
    validation and transitive source-withdrawal closure.
12. A deterministic human review task agenda with dependency DAG checks,
    explicit priorities, finite ready windows, source-policy fences and
    untrusted-content safety holds.
13. A replayable append-only human-review projection with monotonically
    increasing event sequence, expected per-task revision CAS, previous receipt
    digest, exact source-policy and agenda identity. The authoritative
    reviewed-knowledge owner is solely responsible for signing and storing any
    real review; this pure projection never fabricates such authentication.
14. A least-authority Jeeves handoff of exact source-reference metadata and
    bounded review tasks. No source bodies, provider activation, model
    instructions or external work execution are included.
15. Optional human review planning with explicitly supplied effort estimates,
    strict total minutes, dependency-closed selection, per-objective fairness,
    and no claim that estimated minutes were actually measured.
16. A citation manifest with exact Unicode codepoint spans, capture and
    retained-text SHA-256 checks, current source-policy digest and strict
    serialized JSON bounds. It cannot license, publish or verify external
    knowledge by itself.

The authenticated Atlas API returns the graph summary, prioritized review
queue, metadata-only handoff and citation counts. Optional operator-supplied
review_effort estimates let the user select a finite review portfolio. Example
additional request properties:

    "review_effort": [
      {"task_type": "passage_integrity", "estimated_minutes": 10,
       "estimate_basis": "operator_estimate"},
      {"task_type": "objective_gap", "estimated_minutes": 15,
       "estimate_basis": "operator_estimate"}
    ],
    "review_budget_minutes": 120

Every task type in the resulting agenda must have an explicit estimate
before a portfolio can be generated. If estimates are omitted, the portfolio
is null rather than an invented timing claim. No new database, runtime
service, provider credential, crawler transport or scheduling owner is
introduced. The existing authenticated Mongo session and source-use policy
remain the only valid source acquisition and reference authority; a second
live database read fences policy and snapshot changes before responding.

The source-only regression workflow runs the Dragon Atlas, campaign,
invalidation, and review-ops suites after compiling all Python code. These
checks alone do not certify an installed consumer app, live network
acquisition, backend Mongo concurrency, real device execution or release.


## Lexical BM25 and cross-source research intelligence (20-stage Atlas)

The authenticated owner-scoped Atlas route supports an optional retrieval
mode, either fusion (the existing reciprocal-rank pipeline) or lexical_bm25.
The lexical mode is a source-only, deterministic ranker using passage-level
IDF, bounded BM25 term frequency, query coverage, minimum-term phrase
proximity, query-weight saturation, and host/source-fair selection.

The BM25 ranker first **rebuilds the complete ephemeral passage index**
from the original validated source snapshot and current policy exclusions,
then checks the entire indexed receipt before scoring. Consequently a
caller cannot smuggle forged text, source identities, offsets or search
tokens through a constructed index object. Its score is a lexical ranking
heuristic, not calibrated factual probability, source independence, or
external content trust.

The 20-stage source-custody chain adds four final stages:
17. Optional lexical ranking receipt, with real per-query rank positions,
    bounded term/score budgets and a downstream exact-source fusion adapter.
18. Quantitative observation extraction and cross-source difference
    candidates, based on explicit decimal units: kilograms/grams,
    meters/kilometers/miles, times, percentages and unchanged currencies.
    Only comparable unit families are compared. Context overlap is mandatory
    and every discrepancy stays unverified pending human review.
19. ISO date mention detection with exact Unicode offsets, valid calendar
    dates, semantic context hints and source capture-time receipt. A page
    mentioning a date does not prove remote freshness or a real-world event.
20. Optional term-feedback proposals from source-anchored, operator-reviewed
    graded relevance labels. External source text can only suggest terms;
    it can never change the operator's objectives, grant an acquisition
    right, or execute a query by itself.

Set "retrieval_mode": "lexical_bm25" alongside the normal read-only Atlas
POST request to use the new ranking engine. The response now exposes
ranking counts, source-anchored numeric discrepancy coordinates and
date-group metadata, not full page bodies or any verified-knowledge claim.

The capability remains in the same backend/core/dragon_crawler.py owner,
under the existing authenticated route and source-use permission checks.
No new storage owner, provider, network fetcher, executor, migration or
autonomous background service was added. The user-facing review holds,
draft/merge holds, exact-head security gates, real-device qualification and
live backend E2E are unaffected by these inspection features.
