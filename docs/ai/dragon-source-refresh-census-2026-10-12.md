# Dragon crawler — owner-wide freshness census and stale-policy isolation

**Authored:** 2026-10-12 UTC  
**Depends on:** `dragon-source-policy-renewal-and-freshness-2026-10-12.md`

## Operational milestone

A source with an expired external policy receipt must **never** receive a worker ticket. Previously `DragonSourceOperations.ready_candidates` delegated to the canonical `DragonSourceCaptures._policy` verifier, which correctly denied stale permissions but raised a `PermissionError` that aborted the *entire* owner ready scan. A single site whose license or robots review had expired could therefore stop unrelated source scheduling.

The scheduler now catches **only** policy-access denial and excludes the affected source. It does not catch or suppress general integrity `ValueError` from corrupted metadata or stage lineage; invalid receipt corruption remains a non-admission event and must be investigated through the operator audit. No expired policy is used as a fallback.

## Owner-wide read-only refresh census

`DragonSourceRefreshPlanner.scan(owner, now, limit)` evaluates up to 100 persisted source-operation records and returns stable, deterministic results, sorted with actionable expiry, reviewed-source revisit and manual hold cases before unrelated records. It reports tracked source count, due-for-revalidation count, expired policy count and manual holds. The census reuses `assess`, which reads the original source registry, revision capture lineage and recorded rights expiry.

The inspection makes **no network requests**, changes **no queues**, issues **no resource grants**, and cannot certify external page changes, independent knowledge or AI model updates. When owner-scoped batches exceed the cap, callers must narrow the scan rather than silently drop unseen sources.

Trusted read-only operator command:

```sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli refresh-census \
  --database /approved/studio.sqlite --owner studio \
  --now "$(date -u +%s)" --limit 100 --trusted-local-operator
```

## Acceptance tests

Two focused regressions confirm an expired source remains blocked while producing a source-specific renewal signal, and ensure census results enforce owner boundaries and bounded limits. The existing twenty-one source-operations and thirteen Glean tests continue to cover hash-chained custody, replay protection, stage archive, manual policy holds and independently verified Wiki promotion boundaries. Actual test passing is subject to exact-head Python CI.

**Next:** an externally authenticated source-rights attestation service and a production pilot limited to individually permissioned, currently reviewed hosts. The crawler must stay disabled against unassessed sources.
