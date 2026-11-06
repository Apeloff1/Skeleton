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

