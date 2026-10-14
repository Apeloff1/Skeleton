# Dragon crawler — durable idle-only source operations

**Authored:** 2026-10-12 UTC. **Status:** implementation pushed on the Dragon feature branch; no autonomous crawler activated.

## Integration milestone

The existing Dragon source atlas contains **248 candidate URLs in 22 families**, and the signed Tamagotchi dragon nest already supports research planning and per-process global resource admission. This milestone makes **article-worker scheduling crash-conscious**, by adding a persistent, owner-scoped, append-only source-operations journal, per-host cooldown ledger, worker-token fencing, idempotent scheduling, post-acquisition review queue, and explicit stop/recovery custody.

**Source:** `skeleton/ai/game_builder/dragon_technical_source_operations.py`. **Integration:** the existing `acquire_canonical_technical_article` accepts an optional `operations=` binding. `DragonNestSourceOperations` is named `DragonSourceOperations` in code.

### States and rules

```text
trusted operator + completed current policy -> scheduled
  + signed adult nest + independent lane consent + live shared global grant
  + ready-at + host cooldown + no unresolved host/owner worker -> leased
  -> recorded, content-bound capture -> completed -> independent review
  -> no capture or cancelled work -> retry_wait (bounded exponential backoff)
  -> expiry/crash -> quarantined (NEVER automatically release resources)
  -> supervisor verifies actual process stop AND grant reconciliation
  -> acknowledged_stop -> separately recheck policy -> scheduled
```

Reservations are held per `(owner, source)` in SQLite with a hash-chained transition journal, guarded head, and an acquisition-token identity bound to the existing short-lived `HatchlingWorkerTicket`. All mutations use `BEGIN IMMEDIATE` transactions; simultaneous processes cannot independently claim the same source and a second source from the same host must satisfy shared persisted cooldown.

**Expiry is not worker termination.** Expired leases move to `quarantined` and block the whole host from new work until the real worker has been stopped and a trusted supervisor has reconciled global reservations. There is no silent TTL-based resource release. A supervisor-provided external stop receipt is a reference to evidence held by the supervisor; this module checks its shape and trusted input but does not independently validate a remote process manager. Deployments must enforce that trust boundary.

### Network and review safety

Successful source operations still require `DragonNestWorkerAdmission` for real global resource capacity and an independently completed, current policy receipt for robots, terms, reference use, and SSRF safety. The source network adapter uses the existing socket-bound `SafeHttpFetcher`/`CrawlEngine`. With `operations=` bound, it rechecks **both** the durable lease and the live idle/resource grant before robots and content requests, and again before committing captured reference text.

Only the article lane is admitted by this new operations queue. Video workers must use a separate media-policy pipeline, and already-reviewed source recrawls remain under their separate canonical recrawl authority. No video downloads, unauthorized platform resources, automated model training, or permission-free background crawling are introduced.

An article worker releases its shared resource grant only after its synchronous transport has stopped. It then appends a `completed` state bound to the exact newly captured content digest, or `retry_wait` with an increasing delay when no capture is retained. If a process crashes between grant release and journal update, the unresolved lease is quarantined on recovery rather than silently re-used.

Completed work appears in `review_queue`, which verifies that the current `DragonSourceCaptures` revision matches the durable completion receipt. These are **pending independent review records**, not accepted facts. The existing Glean Matrix, Wiki and HOAG review roles remain the sole knowledge-admission and memory authorities.

### Trusted operator workflow

```python
# Construct using the same canonical owner-scoped DB and the live signed nest
operations = DragonSourceOperations(captures)
operations.schedule(owner, source_id, now=clock, ready_at=clock,
                    authorized=True, trusted_worker=True)
preview = admission.begin(owner, sample=sample, at=utc_now,
    idle_since=verified_last_activity, now_seconds=telemetry_clock,
    authorized=True, trusted_worker=True, consented=True,
    article_consent=article_consent, video_consent=False, updates_consent=False)
if preview.admitted:
    operations.attach(preview.ticket, admission, now=clock,
                      authorized=True, trusted_worker=True)
    # The trusted authorized worker calls acquire_canonical_technical_article
    # with operations=operations. This handles rechecks, stop and journal exit.
```

**Important:** if `attach` is rejected, the caller must acknowledge `admission.stopped` after confirming no network work has started; the in-process resource grant has already been issued. No outer app automation should silently swallow this error or assume the granted resources are free.

Read-only CLI examples:

```sh
python -m skeleton.ai.game_builder.dragon_technical_source_cli operations-inspect \
  --database /path/to/owner.sqlite --owner studio \
  --source-id source-<64hex> --trusted-local-operator

python -m skeleton.ai.game_builder.dragon_technical_source_cli operations-review \
  --database /path/to/owner.sqlite --owner studio \
  --limit 50 --trusted-local-operator
```

### Test plan

`tests/test_dragon_technical_source_operations.py` provides eight tests for canonical policy/idempotent scheduling, persistent lease and foreground/consent denial, successful capture/review queue, mismatched capture and replay rejection, fail-closed crash quarantine, external stop reconciliation, corrupt event/head detection, and the actual article-fetch adapter using an offline robots/page transport, including revocation and backoff. The workflow includes this module in its Dragon Python suite.

### What is still not production-activated

No live page was downloaded in this implementation turn; the offline transport tests do not prove that network access is available or permitted for each source. The operator/supervisor must supply verified idle telemetry, physical process stop signals, host permission evidence, durable global scheduler reconciliation, bounded delayed-job activation, safe per-host egress policies, and authoritative Wiki/HOAG approvals. In-memory `DragonResourceSession` is still not a cross-process resource accounting service. The durable lease ledger is one **additional fence**, not a substitute for distributed global-resource accounting. No source is converted to neural weights.

**Next:** roll out externally supervised runtime work on specifically licensed/approved sources, verify acquisition results and recrawl clock behavior, and benchmark measured game-building improvements through sandbox challenge/holdout evidence before shadow-weight promotion.
