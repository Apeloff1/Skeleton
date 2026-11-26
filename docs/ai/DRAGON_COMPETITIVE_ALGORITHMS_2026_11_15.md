# Dragon competitive algorithm review — 2026-11-15

Scope: ten comparison implementations selected for distinct strengths, not a statistically ranked top ten. Reviewed documented techniques, not proprietary service internals. Original Dragon code retains existing policy boundaries. No external competitor was executed and no throughput, quality, compliance, or superiority claim follows from source inspection alone.

| Engine | Documented approach | Dragon response and remaining gap |
| --- | --- | --- |
| Scrapy | Latency/target-concurrency feedback, smoothed delay, errors cannot reduce delay; disk duplicate filters | Transport-only measurements; tail latency, asymmetric controller, durable request/byte conservation. Large persistent frontier still missing. |
| Crawlee | Resource snapshotting and autoscaled concurrency, cgroup-aware pressure | Actual local physical-credit admission uses tightest known host/cgroup headroom, CPU quota, PSI and hysteresis. Original global credit ceiling stays four; no unlimited distribution. |
| Nutch | Change/no-change adjustment to bounded revisit interval | Existing temporal and freshness observation contracts are a foundation; historical change-hazard estimation and explicit revalidation under new consent remain work. |
| StormCrawler | Partitioned host queues, streaming fetch/parse/status feedback | Canonical per-run outcome feedback and disposable parsing; distributed origin coordination and durable streaming frontier still outstanding. |
| Heritrix | One URI per host at a time; fetch-duration-based delay and bandwidth policy | Post-settlement adaptive delays use robust tail statistics and measured bytes; owner-run host timing never overrides remote restrictions. WARC export and independent archive benchmarks remain unqualified. |
| Colly | Async parallelism, domain rate rules, pluggable visited storage, connection reuse | Existing global physical slice credits plus pressure-limited admission, exact duplicate receipts; no claim of Go-level throughput or HTTP pooling parity. |
| Crawl4AI | Relevance × novelty × authority, coverage/consistency/saturation, statistical and embedding strategies | Bounded rarity-weighted actual evidence coverage, conservative host yield, expected cost and exploration, no unsupported domain-authority score, no fabricated confidence in truth. Semantic embedding and validation-based stopping remain gaps. |
| Firecrawl | Main-content extraction, structured output formats, sitemap mapping, cache age and change tracking | Explicit structural confidence + fallback, existing typed extractors and durable provenance. Headless rendering and cross-session conditional recrawl are not implemented in this pass. |
| Scrapling | Adaptive element relocation by similarity, asynchronous checkpointed spiders, throttle | Selector-independent landmark/density extraction and hard ambiguity fallback. Not a full arbitrary selector relocation system; no access-control bypass or identity manipulation. |
| Katana | Scoped discovery, depth, global/per-host rate controls and standard/headless engines | Existing strict canonical scope and depth; measured strategy never admits URLs itself. Browser execution and large-scale endpoint inventory not qualified. |

## Source references

- Scrapy AutoThrottle: https://doc.scrapy.org/en/master/topics/autothrottle.html
- Scrapy settings: https://docs.scrapy.org/en/latest/topics/settings.html
- Crawlee Python scaling: https://crawlee.dev/python/docs/concepts/scaling-crawlers
- Nutch adaptive fetch: https://nutch.apache.org/documentation/javadoc/api/org/apache/nutch/crawl/AdaptiveFetchSchedule.html
- StormCrawler architecture: https://github.com/apache/stormcrawler/blob/main/docs/src/main/asciidoc/architecture.adoc
- Heritrix: https://heritrix.readthedocs.io/en/stable/configuring-jobs.html
- Colly: https://go-colly.org/docs/best_practices/crawling/ and https://go-colly.org/docs/examples/parallel/
- Crawl4AI: https://docs.crawl4ai.com/advanced/adaptive-strategies/ and https://docs.crawl4ai.com/core/adaptive-crawling/
- Firecrawl: https://github.com/firecrawl/firecrawl-docs/blob/main/advanced-scraping-guide.mdx and https://github.com/firecrawl/firecrawl-docs/blob/main/features/map.mdx
- Scrapling: https://scrapling.readthedocs.io/en/latest/index.html
- ProjectDiscovery Katana: https://github.com/projectdiscovery/katana/blob/dev/README.md

## Implemented formulas

All policies remain prior to scoring. Eligible URL means already admitted, due, and still subject to transport DNS, robots, consent, byte reservation and lease checks.

- Acquisition ledger: settled requests = total requests - pending dispatch; sum known bytes = charged bytes; sum unknown bytes plus pending reservation = reserved bytes. A failed or interrupted request cannot disappear from the accounting after replay. Durations are quantized to 250 ms; no source headers or arbitrary body strings are recorded in the ledger.
- Per-host latency: EMA = 0.75 previous + 0.25 latest observed duration; censored unknown measurements do not invent latency. Target = max(operator floor, 1.25 × max(0, EMA - 0.25)). Healthy updates smooth 85% previous / 15% target. Failures never shorten the active hold and increase controller delay multiplicatively. Upper-tail observation (nearest-rank p90) adds a conservative floor. Existing server and robots readiness are combined using max(), never min().
- Query rare-term weight = min(3, 1 + ln((1 + candidate count)/(1 + candidate term frequency))). Coverage uses actual unique retained source text, not URL labels. Missing contribution = 1/(1 + distinct observed hostnames)^2; distinct hostnames are **not** proof of source independence.
- Host reliability = (2 + successful transport observations)/(4 + observed requests), reduced by bounded uncertainty. Query-hit posterior and novelty posterior have finite priors. No unsupported domain prestige score.
- Marginal gain = 0.45 relevance + 0.35 remaining weighted gap + 0.20 novelty. Expected cost = 1 + 0.22 ln(1 + latency) + 0.18 ln(1 + bytes/65536) + 0.42 uncached robots overhead + 0.20 attempts + 0.05 depth. Priority = shrunk reliability × marginal gain / cost + bounded exploration + origin diversity + bounded queue age. If only one request remains, a cold origin's marginal priority is discounted. Coverage strategy combines 80% marginal priority with 20% previous metadata coverage. Coefficients are engineering defaults, not fitted performance optima.
- Resource governor: available memory is the tightest observed physical/cgroup/ancestor headroom; new slice capacity is bounded by floor((headroom - 256 MiB)/640 MiB), effective CPU cores, PSI thresholds and original maximum four. Missing memory/CPU metrics restrict to one. Critical observed pressure stops new admissions. Decrease immediately; increase one slot after three seconds of stability. Existing leased operations do not lose ownership. This is a Linux-oriented admission heuristic, not proof of device-specific safe memory use.
- Structural HTML confidence combines sufficient main/article characters, prose blocks, punctuation/word/landmark density and surrounding chrome. A narrow projection requires multiple substantive prose blocks, a minimum content fraction, surrounding chrome and confidence >= 0.70. Ambiguous layouts preserve the ordinary extraction. Links retain the original discovery path and full canonical safety gate. All projected text remains unverified evidence.

## Evaluation and limits

The offline runner compares FIFO, balanced, URL-only coverage ablation, and the new coverage strategy under identical fixtures and runtime admission. It reports recall, precision, yield per request and KiB, policy/duplicate costs, recovery, trace and source-set fingerprints, and checkpoint size. Every executed run must satisfy exact byte/request conservation and zero forbidden fixture requests. There are three workloads and three repetitions in CI (36 planned runs). These are fixture evaluations, not executions of the ten competitors. Do not use synthetic recall or synthetic timing as a claim of public-web performance.

Remaining priorities: cross-session origin-wide lease/pacing, distributed durable frontier with validated partitions, incremental revision and conditional fetch under explicit consent, stronger process sandbox and platform-specific parser limits, browser sandbox with separately approved scopes, selector relocation and evidence validation, fair external-engine benchmark under the same authorized corpus. The code binding changes; historical snapshots cannot be silently migrated. Exact-head source, backend, UI, architecture, security and device qualification must pass before promotion. No merge or release authorization.
