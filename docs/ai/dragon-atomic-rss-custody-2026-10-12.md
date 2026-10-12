# Dragon Updates hatchling — atomic verified RSS handoff
**Timestamp:** 2026-10-12 UTC · **PR:** #3605 · **Scope:** no autonomous network fetch, no neural-weight change

## Defect closed
The signed RSS snapshot queue and the host-fair durable RSS due scheduler previously completed their SQLite writes independently. A crash, stale compare-and-swap, or lost idle-worker admission between these calls could leave unverified feed items persisted without corresponding scheduler advancement, or vice versa.

## New strict transaction boundary
`DragonVerifiedRssPoll.accept` requires both pre-existing components to share the same operator-controlled SQLite connection. It verifies the trusted source/ticket/owner and exact RSS feed URL, scheduled revision and due time, independently signed fetched snapshot, and its rights-receipt digest against the registered scheduling policy. The existing source admission gate is rechecked by the queue, scheduler, and one more time just before the transaction is committed.

Both queue ingestion and scheduler advancement accept an explicit trusted `transaction_managed=True` argument to join the outer `BEGIN IMMEDIATE` transaction. Their legacy default stays `False`, preserving previous standalone usage. The orchestrator owns the outer commit or rollback. A valid snapshot plus an expired/stale ticket cannot partially write research items. Replay retains the prior immutable HMAC chain and signed snapshot receipts. The route remains metadata-only, operator-driven and rights-safe.

## Adversarial checks
Tests prove atomic success, owner- and source-scoped custody, idempotency across retries, rollback on injected scheduler crash, full rollback when foreground work preempts the idle hatchling just before commit, foreign owner / wrong URL / too-early / stale generation refusal, invalid signature and mismatched existing rights, and rejection of queue/scheduler components backed by different SQLite connections.

## Authority boundaries and follow-up
A successful transaction only creates `unverified_update_lead` research entries; it does not crawl the network, grant website rights, declare article facts true, approve shadow/normal/hyper weights, or touch the neural model. Production fetchers still need independent rights and robots/terms checks and real idle worker admission. This strict entry point must be called by production orchestration rather than assuming existing code will automatically switch.

**Improvement record (2026-10-12 UTC):** (signed RSS evidence and scheduler scheduling now commit atomically); (preempted or failed batches rollback without orphaned queue rows); (retries remain bounded by exact source, external signed receipt and expected scheduler generation).