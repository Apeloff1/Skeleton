# Backend core v1 contract (`skeleton.backend_core.v1`, version 1.1.0)

Audience: Middleware (mounting, auth, dispatch scheduling) and Frontend (webhook settings UI).
Code: `backend/core/core_v1/` (domain + ports + adapters), `backend/core/core_v1_webhooks.py`
(composition root), `backend/routes/core_v1_webhooks.py` and `backend/routes/core_v1_delivery_ops.py`
(HTTP adapters). Tests: `tests/backend_core/`.

## Architecture
Hexagonal. `service.WebhookService` depends only on `ports.py` protocols. Adapters:
SQLite (`sqlite_store.py`, on `skeleton.persistence.app_foundation.db.Database`, own
`core_v1_migrations` ledger), in-memory (`memory_store.py`), HTTP transport (`transport.py`,
public-HTTPS policy from `skeleton.security.outbound_url`, no redirects).
Nothing under `skeleton/persistence` was modified (that tree is AIFT-mirrored and SHA-pinned).

## Mounting (Middleware-owned)
The router is **not** registered in `core.routes_registry.KNOWN_ROUTES`. To enable:
```python
from routes import core_v1_webhooks
core_v1_webhooks.install_error_handler(app)
app.include_router(core_v1_webhooks.router)
from routes import core_v1_delivery_ops          # 1.1: delivery log, DLQ, retry policy, secrets admin
app.include_router(core_v1_delivery_ops.router)
```
Env: `SKELETON_BACKEND_CORE_DB` (default `data/backend_core_v1.sqlite3`),
`SKELETON_BACKEND_CORE_CURSOR_KEY` (set in multi-process deployments so cursors survive restarts),
`SKELETON_BACKEND_CORE_KEKS` / `SKELETON_BACKEND_CORE_ACTIVE_KEK` / `SKELETON_BACKEND_CORE_REQUIRE_KEK`
(secrets at rest, below).
Dispatch: call `get_runtime().webhooks.dispatch_due(limit)` periodically (e.g. every 5 s) from a
worker. Leases (60 s) make concurrent/crashed workers safe; a stale completion is discarded.

## Auth
`routes.gameforge_auth.get_current_user`. Unauthenticated, anonymous and `dev_mode` users get 401
(fail closed). Tenant = `user.tenant_id` (default `"default"`). Writes need role
`owner|admin|editor`; reads any authenticated role. Cross-tenant ids return 404.

## Error envelope
`{"error": {"type", "code", "message", "context"}}` — same shape as projects v1.
Codes are listed in `errors.CODES` (stable; additions are minor-version changes).

| status | codes |
|---|---|
| 400 | `CORE.WEBHOOK.INVALID`, `CORE.WEBHOOK.INVALID_URL`, `CORE.EVENT.INVALID`, `CORE.PAGINATION.INVALID_LIMIT`, `CORE.PAGINATION.INVALID_CURSOR`, `CORE.IDEMPOTENCY.INVALID_KEY`, `CORE.REQUEST.INVALID_JSON`, `CORE.DELIVERY_LOG.INVALID_FILTER`, `CORE.DLQ.INVALID`, `CORE.RETRY_POLICY.INVALID`, `CORE.SECRETS.INVALID_JOB` |
| 401/403 | `CORE.AUTH.UNAUTHENTICATED`, `CORE.AUTH.FORBIDDEN` |
| 404 | `CORE.WEBHOOK.NOT_FOUND`, `CORE.DELIVERY.NOT_FOUND`, `CORE.EVENT.NOT_FOUND`, `CORE.RETRY_POLICY.NOT_FOUND` |
| 409 | `CORE.WEBHOOK.LIMIT_REACHED` (25 active/tenant), `CORE.WEBHOOK.DISABLED`, `CORE.DELIVERY.NOT_REPLAYABLE`, `CORE.IDEMPOTENCY.KEY_REUSED`, `CORE.IDEMPOTENCY.IN_FLIGHT`, `CORE.SECRETS.NO_KEYRING` |
| 412/428 | `CORE.CONCURRENCY.PRECONDITION_FAILED` (response carries current `ETag`), `CORE.CONCURRENCY.PRECONDITION_REQUIRED` |
| 503 | `CORE.STORE.UNAVAILABLE` |

## Conventions
- **Pagination:** `?limit=1..200` (default 50) `&cursor=`; response `{items, next_cursor, has_more}`.
  Cursors are HMAC-signed and bound to tenant + collection (+ status filter); order is `(created_at, id)`.
- **Concurrency:** resources carry `version` and strong `ETag` `"<id>.<version>"`. PATCH, DELETE,
  rotate-secret require `If-Match` (428 if missing, 412 if stale; `*` allowed).
- **Idempotency:** `Idempotency-Key` (8–128 `[A-Za-z0-9_\-:.]`) on `POST /webhooks` and replay.
  Scoped per tenant+actor+route, 24 h TTL. Same body → stored response with
  `Idempotent-Replayed: true`; different body → 409. 5xx responses are not stored.
- **Events** dedupe on `dedupe_key` per tenant (200 + `duplicate: true` on repeats).

## Endpoints (prefix `/api/v1/core`)
| method | path | notes |
|---|---|---|
| POST | `/webhooks` | body `{url, event_filters?, description?, max_attempts? (1..20, default 8)}`; 201; returns `secret` **once** |
| GET | `/webhooks` | paginated |
| GET | `/webhooks/{id}` | `ETag` header |
| PATCH | `/webhooks/{id}` | any of `url, event_filters, description, active, max_attempts` |
| DELETE | `/webhooks/{id}` | soft delete (`active=false`, `disabled_reason="deleted"`) |
| POST | `/webhooks/{id}/rotate-secret` | returns new `secret`; previous secret co-signs until next rotation |
| GET | `/webhooks/{id}/deliveries` | paginated, `?status=pending|in_flight|succeeded|failed|dead` |
| GET | `/deliveries/{id}` | includes `attempt_log` |
| POST | `/deliveries/{id}/replay` | 202; only terminal deliveries; new delivery with `replay_of` |
| POST | `/events` | `{type, data, dedupe_key?}`; 202 with `deliveries_created` |

### 1.1 additions (`routes/core_v1_delivery_ops.py`)
| method | path | role | notes |
|---|---|---|---|
| GET | `/deliveries` | any | tenant-wide log; `?webhook_id&event_id&status=a,b&since&until&time_field=created_at|updated_at` |
| GET | `/events/{id}/deliveries` | any | fan-out of one event; `?status` |
| GET | `/attempts` | any | attempt log; `?webhook_id&event_id&delivery_id&outcome=success,retry,dead&since&until` |
| GET | `/webhooks/{id}/attempts` | any | same, one subscription |
| GET | `/dlq` | any | dead deliveries ordered by time of death (`updated_at`); `?webhook_id&since&until` |
| POST | `/dlq/redrive` | owner/admin/editor | `{delivery_ids:[≤100]}` **or** `{webhook_id?, since?, until?, limit≤100}`; 202 `{requested, redriven[{delivery_id, replay_id}], skipped[{delivery_id, reason}]}` |
| POST | `/dlq/purge` | owner/admin | `{older_than_seconds: 3600..31536000, webhook_id?, limit≤1000}`; hard-deletes dead deliveries + attempts; `has_more` when the limit was hit |
| GET | `/webhooks/{id}/retry-policy` | any | effective policy + `override` flag |
| PUT | `/webhooks/{id}/retry-policy` | owner/admin/editor | `{base_seconds 1..3600, factor 1..10, cap_seconds 1..604800 (≥ base), max_age_seconds 60..2592000|null}`; unset fields inherit the service default |
| DELETE | `/webhooks/{id}/retry-policy` | owner/admin/editor | 204; 404 if no override |
| GET | `/admin/secrets/status` | owner/admin | `{active_key_id, plaintext_rows, stale_key_rows, rows_by_key, encrypt_job, rewrap_job}` |
| POST | `/admin/secrets/encrypt` | owner/admin | body optional `{batch_size≤1000, max_batches≤100, force}`; resumable job report |
| POST | `/admin/secrets/rewrap` | owner/admin | same; rewraps every envelope onto the active key |

- Times: ISO-8601 with zone (`Z`/offset) or unix seconds; windows are half-open `[since, until)`.
- Cursors are additionally bound to a digest of the filter set, so a cursor from one filter is 400
  under another (or another tenant).
- Redrive reuses replay semantics (new delivery with `replay_of`). It is idempotent per dead delivery:
  one with an open (non-terminal) replay is skipped with `replay_in_progress`.
- Retry policy: per-subscription override of backoff; `max_age_seconds` dead-letters a delivery
  (`last_error` contains `policy:max_age`) once the next retry would land past that age.
  `max_attempts` stays on the subscription.
- Secrets admin routes are operator tools and act on the whole store, not one tenant; restrict
  `owner`/`admin` accordingly in multi-tenant deployments.

Event filters: dotted lowercase segments; `*` matches exactly one non-leading segment (`project.*`).
Empty filter list = all events. Payload ≤ 64 KiB JSON object.

## Delivery wire format (receivers)
`POST <url>` JSON `{id, type, created_at, delivery_id, data}` with headers
`Skeleton-Signature: t=<unix>,v1=<hex>[,v1=<hex>]` (HMAC-SHA256 of `"<t>." + body`),
`Skeleton-Event-Id`, `Skeleton-Event-Type`, `Skeleton-Delivery-Id`, `Skeleton-Delivery-Attempt`.
Verify with any listed `v1` and reject `|now - t| > 300 s`. 2xx = success; 408/409/425/429/5xx and
network errors retry with capped exponential backoff (10 s base, 6 h cap, deterministic jitter);
410 and other 4xx dead-letter immediately. Redirects are not followed.

## Secrets at rest (1.1)
Signing secrets are sealed with an AES-256-GCM envelope (`envelope.py`, `cryptography` AESGCM):
`"CSE" 0x01 | kid_len | kid | wrap_nonce(12) | wrapped DEK(48) | data_nonce(12) | ciphertext+tag`.
A random per-secret DEK encrypts the secret; the KEK named by `kid` wraps the DEK. AAD binds
`core_v1.webhook_secret|<tenant>|<secret_id>` (a blob copied to another row/tenant will not open)
and the header. Rotation only rewraps the DEK.

- **KeyProvider port** (`keys.py`): `active_key_id()`, `get(kid)`, `key_ids()`. Shipped:
  `StaticKeyProvider` (tests/composition) and `EnvKeyProvider`:
  `SKELETON_BACKEND_CORE_KEKS="k2025:<b64 32 bytes>,k2026:<b64>"`,
  `SKELETON_BACKEND_CORE_ACTIVE_KEK=k2026` (required with >1 key). A KMS provider only has to
  implement the same three methods.
- **No keyring:** secrets stay plaintext (warning logged) unless `SKELETON_BACKEND_CORE_REQUIRE_KEK=1`,
  which makes `build_runtime` fail. Production should set it. A plaintext runtime refuses to sign
  with an encrypted row rather than send ciphertext as a key.
- **Migration:** schema migration 4 adds `key_id` ('' = plaintext) to `core_v1_webhook_secrets`,
  plus `core_v1_job_checkpoints` and `core_v1_retry_policies`. Data migration is an online job
  (`secret_migration.SecretMigrator`, or `POST /admin/secrets/encrypt`): batched by `secret_id`,
  checkpointed after each batch (resumable after a crash), compare-and-set per row (never clobbers a
  concurrent write), idempotent (a finished job is a no-op; `force` re-scans). Legacy plaintext rows
  stay readable during the migration.
- **Rotation:** add the new key to `KEKS`, switch `ACTIVE_KEK`, deploy, run `/admin/secrets/rewrap`
  until `done`, check `/admin/secrets/status` shows `stale_key_rows: 0`, then drop the old key.
- A row that can't be opened (missing key) makes its delivery **retry**, not dead-letter, so
  restoring the key recovers delivery.

## Known limits
- Without a keyring webhook secrets are stored as raw bytes; see above.
- Secrets jobs run inline in the request (bounded by `batch_size × max_batches`); call repeatedly
  until `done` for large stores.
- `matching()` filters in Python after a tenant-scoped query (≤ 25 active per tenant).
