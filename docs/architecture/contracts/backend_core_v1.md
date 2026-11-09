# Backend core v1 contract (`skeleton.backend_core.v1`, version 1.0.0)

Audience: Middleware (mounting, auth, dispatch scheduling) and Frontend (webhook settings UI).
Code: `backend/core/core_v1/` (domain + ports + adapters), `backend/core/core_v1_webhooks.py`
(composition root), `backend/routes/core_v1_webhooks.py` (HTTP adapter). Tests: `tests/backend_core/`.

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
```
Env: `SKELETON_BACKEND_CORE_DB` (default `data/backend_core_v1.sqlite3`),
`SKELETON_BACKEND_CORE_CURSOR_KEY` (set in multi-process deployments so cursors survive restarts).
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
| 400 | `CORE.WEBHOOK.INVALID`, `CORE.WEBHOOK.INVALID_URL`, `CORE.EVENT.INVALID`, `CORE.PAGINATION.INVALID_LIMIT`, `CORE.PAGINATION.INVALID_CURSOR`, `CORE.IDEMPOTENCY.INVALID_KEY`, `CORE.REQUEST.INVALID_JSON` |
| 401/403 | `CORE.AUTH.UNAUTHENTICATED`, `CORE.AUTH.FORBIDDEN` |
| 404 | `CORE.WEBHOOK.NOT_FOUND`, `CORE.DELIVERY.NOT_FOUND` |
| 409 | `CORE.WEBHOOK.LIMIT_REACHED` (25 active/tenant), `CORE.WEBHOOK.DISABLED`, `CORE.DELIVERY.NOT_REPLAYABLE`, `CORE.IDEMPOTENCY.KEY_REUSED`, `CORE.IDEMPOTENCY.IN_FLIGHT` |
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

Event filters: dotted lowercase segments; `*` matches exactly one non-leading segment (`project.*`).
Empty filter list = all events. Payload ≤ 64 KiB JSON object.

## Delivery wire format (receivers)
`POST <url>` JSON `{id, type, created_at, delivery_id, data}` with headers
`Skeleton-Signature: t=<unix>,v1=<hex>[,v1=<hex>]` (HMAC-SHA256 of `"<t>." + body`),
`Skeleton-Event-Id`, `Skeleton-Event-Type`, `Skeleton-Delivery-Id`, `Skeleton-Delivery-Attempt`.
Verify with any listed `v1` and reject `|now - t| > 300 s`. 2xx = success; 408/409/425/429/5xx and
network errors retry with capped exponential backoff (10 s base, 6 h cap, deterministic jitter);
410 and other 4xx dead-letter immediately. Redirects are not followed.

## Known limits
- Webhook secrets are stored as raw bytes in the core DB (needed to sign); protect the DB file
  like other credential stores. Encryption at rest is a follow-up for a KMS-backed `SecretRepository`.
- `matching()` filters in Python after a tenant-scoped query (≤ 25 active per tenant).
