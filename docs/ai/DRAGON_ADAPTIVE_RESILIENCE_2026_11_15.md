# Dragon adaptive resilience and source-authority boundary
Date: 2026-11-15. Status: implementation candidate, review only.

## Authority and threat model
The existing CrawlRun and owner-scoped CORE_DB application remain the sole dispatch and checkpoint owners. The crawler treats source text, titles, markup, agent configuration files, extracted documents, unknown embedded directives, and robots comments as external data. Site-provided access and retention restrictions are honored; arbitrary source instructions are not an authorization. A source never changes tool permission, request scope, identity, credentials, consent, code or grant.

A bounded deterministic inspection precedes discovery, retention, and retrieval. Known instruction artifacts are quarantined regardless of pattern score. Unicode compatibility normalization, formatting-code removal, HTML entity decoding, and a second split-markup view detect common indirect-instruction forms. Pattern categories are heuristic signals, not proof of malice: legitimate security documentation may be held. A no-hit result is not permission to execute anything. Current code does not claim to detect every encoding, language, binary, or semantic attack.

The same canonical snapshot commits incidents and the charged response outcome. The incident ledger is separate from the rolling 64-event diagnostic tail, bounded by the finite request budget. It records stage, sequence, URL digest, category counts and permitted input/match fingerprints, not raw instructions. Site retention restrictions suppress source fingerprints; no raw attack payload is copied into a new store. Inspecting robots comments does not override valid rules. The authenticated UI exposes bounded metadata and host observations; ordinary search, export and source context reject held sources, not merely label them.

## Fault recovery and adaptive operation
The already-admitted frontier remains the only candidate set. Balanced and coverage strategies blend operator-query/URL utility with bounded Beta-prior outcome estimates. FIFO selection remains compatible. Local outcome events provide evidence; source prose does not set priority or change credentials. Repeated transient failures extend host-wide cooldown. Access denials (401/403/451) hold further automatic acquisition from the affected host until the current consent horizon. Existing server Retry-After, robots delays, scope, reservations, lease fencing, physical custody and cancellation retain precedence. Cross-origin recovery never invents alternate identities or access paths. Redirects and restored destinations are subjected to structural and credential-bearing URL vetoes.

Robots processing has a 512 KiB per-policy capacity under the default application response limit, a finite shared cache and an explicit reserve for deny policies. Smaller operator byte budgets, malformed data and exhausted capacity fail closed; no rule truncation grants access. RFC 9309 requires at least 500 KiB parsing capacity, and its rules do not constitute access authorization. Existing Python robots matching behavior and all RFC parsing edge cases still require independent conformance review. This is not a legal certification.

## Comparator benchmark program
Use identical authorized, isolated fixture origins, URL graph, corpus version, request/byte/deadline budgets, machine profile, identity policy, access restrictions and failure seeds. Record exact engine revisions, dependencies and configuration, dataset digest, source rights, event traces and test harness revisions. Candidate set, not a ranked global top ten:
- Scrapy; Crawlee; Crawl4AI; Firecrawl; Colly.
- Apache Nutch; Apache StormCrawler; Heritrix; Scrapling; Katana.

These engines address different workloads. No vendor score, throughput claim or rank is inferred. Test three repetitions per engine per corpus (static graphs, structured feeds, archives, dynamic authorized test pages where supported, multilingual source text, hostile links, injection, denied paths, rate limiting, restart interruption, and storage fault injection). Where a feature is unsupported report unsupported, not zero latency or false success. No production website or anti-bot bypass is used as a benchmark target.

Pre-register metrics:
- zero unauthorized dispatch, zero secret and source-instruction execution, zero quota/robots hold violations (hard eligibility gates);
- relevant unique document recall and precision within equal request/byte budget;
- exact canonical URL/retained text integrity and duplicate rate;
- distinct origin/URL-family coverage;
- recovery time p50/p95 and lost or duplicated committed receipts after fault;
- instruction quarantine recall and false-positive rate against labelled content;
- throughput, peak RSS, disk pressure, network bytes per useful source, end-to-end p50/p95 latency;
- performance under source denial and hostile or malformed content.
Report per-workload results and Pareto comparisons; do not claim universal superiority from a single metric. The equal-budget fixture in the canonical regression suite tests coverage-versus-FIFO yield on one controlled workload. It does not run any external competitor.

## Qualification
Run exact-head tests/test_ai_webcrawler_dragon_adaptive_instruction_guard.py, tests/test_ai_webcrawler_dragon_host_backpressure.py and backend/tests/test_dragon_restorative_recovery.py; adjacent crawler and source-retrieval suites; frontend typecheck and actual operator journey; construction, source/mirror, dependency, security, workflow and repository gates. Verify native/device recovery and live network behavior only under separately authorized bounded conditions. Old snapshots retain their exact implementation digest; migration must never rewrite past authorization or fabricate receipts. Revert the candidate and use its matching snapshot version only after independently reviewed rollback. No merge, release, security certification, compliance guarantee or vendor superiority is claimed.
