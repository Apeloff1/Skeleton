# Dragon crawler — robots-delay custody and long-horizon idle recrawling
**Authored:** 2026-10-12 UTC  
**Branch:** `feat/dragon-wisdom-review-20261010` (PR #3605)  
**Scope:** 248 curated editorial candidates; only sources with an independent current policy receipt may proceed.

## Milestone delivered

Robots.txt can request crawl delays longer than the 60-second Dragon hatchling ticket. In the previous worker implementation a delay greater than five seconds ended the worker with a generic backoff. Repeating those requests risked unnecessary robots probes, improper host cooldown, and bad resource use.

The article capture worker now reads the site's **actual robots Crawl-delay** through the existing `CrawlEngine` / `RobotsCache` policy. It distinguishes four outcomes:

| Observed robots policy | Worker behavior | Durable state |
| --- | --- | --- |
| 0–5 seconds or unspecified | Existing bounded synchronous fetch under live idle/resource consent | Captured review queue or bounded retry |
| Over five seconds through seven days | **No page fetch**; stop worker and release the shared resource grant | `retry_wait` with exact measured cooldown in seconds |
| Over seven days | **No page fetch**; stop and require operator rights/policy inspection | Terminal `policy_hold` and host cooldown set to the supported epoch ceiling |
| Invalid/unsafe crawl-delay value | **No page fetch**; stop and require operator intervention | `policy_hold` |

### Resource discipline

The durable `DragonSourceOperations.release` call still requires an actual live worker stop acknowledged by `DragonNestWorkerAdmission`, a matching lease identity and an authenticated trusted worker. For genuine deferrals it appends a source-bound receipt showing `retry_cause=robots_crawl_delay` and `robots_delay_seconds`, then extends the host cooldown **inside the same SQLite transaction**. Other sources on the same host cannot bypass that cooldown simply because the delayed source released its slot.

A worker that is no longer idle or loses consent does not receive a new request. Foreground activity and global resource admission remain higher-priority than any scheduled research. A robots deferral never authorizes fetching, content retention, source use, Wiki acceptance, shadow weights or permanent training.

### Trusted scheduling

`DragonResearchSupervisor` and `DragonSourceOperations.ready_candidates` already restrict dispatch to owner-scoped sources in a validated policy stage, with an elapsed durable source time and host cooldown. This milestone feeds them the **observed robots delay** rather than a generic retry. When the delay expires, the operator must still have current source rights, robots verification, and a newly granted idle-only worker ticket. If the source policy receipt has expired, the existing `_policy` verifier rejects resumption until new authorization is arranged through the canonical review process.

A terminal `policy_hold` is deliberately not auto-rescheduled or silently cleared, even if enough wall-clock time passes. It requires a separately designed and authorized manual-policy reset workflow; there is no implementation that bypasses it.

### Regression coverage

Four new offline-network scenarios extend `tests/test_dragon_technical_source_operations.py`:

1. 180-second robots delay creates a durable `retry_wait` and matching host cooldown; no article is fetched or long sleep performed, and another operations instance observes the same ready time.
2. A two-day delay produces a two-day source ready time without holding the worker or pretending the original permissions survive that whole period.
3. A robot delay longer than one week creates a manual `policy_hold`, suppresses automatic source reentry and applies host cooldown.
4. Forged deferral reasons and inconsistent manual-hold arguments are rejected before mutating worker lease records.

The test suite still covers signed nest admission, global resource grants, foreground preemption, worker-stop acknowledgment, rights review, event-chain tampering and Wiki/HOAG handoffs. GitHub workflow success must be checked on the exact commit before these tests may be reported as passed.

### No network execution in this work pass

All new tests use an offline HTTP fixture returning robots.txt data. The full source library is still an editorial candidate set; its member websites have not been collectively fetched, approved for training, or measured as independent sources. The Dragon's autonomous production runtime still requires verified OS process-stop evidence and an externally supervised deployment.

### Next production step

Add a durable, independent robots-policy revalidation order with site-specific permission receipts and supervised rearming of `policy_hold`. Then introduce media-specific video processing with restricted rights checks, and measured adversarial game-building improvements before shadow-weight promotion.
