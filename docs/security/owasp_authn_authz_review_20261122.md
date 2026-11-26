# AuthN/AuthZ and OWASP review: backend (2026-11-22, lane B)

Scope: `backend/routes/gameforge_auth.py`, `backend/core/auth_security.py`, the
middleware stack in `backend/server.py`, and a grep-level sweep of `backend/routes`
and `backend/core` for OWASP Top 10 (2021) and API Security Top 10 (2023) patterns.

## Fixed in this change

| ID | OWASP | Finding | Fix |
|---|---|---|---|
| F1 | A02, A07 | Opaque OAuth session tokens were stored in plaintext in `user_sessions`, so a database read gave working bearer tokens. | Tokens are stored as `sha256:<hex>`. Legacy plaintext rows still authenticate and are migrated to the hashed form on first use. A presented value that looks like a digest is never matched verbatim, so a leaked row is not a credential. Logout deletes both forms. |
| F2 | A07 | bcrypt silently truncates at 72 bytes: two passwords sharing a 72-byte prefix were interchangeable. | Registration rejects passwords over 72 UTF-8 bytes. Login input is bounded at 1024 characters and keeps the historical behaviour for existing accounts. |
| F3 | A07, API2 | JWTs were accepted without `exp`, `iat` or `sub`. | `jwt.decode(..., options={"require": ["exp", "iat", "sub"]})`. Tokens this service mints always carry these claims. |
| F4 | A04, A08 | The OAuth provider response was trusted structurally: a non-dict body or non-string fields raised server errors, or could store non-string tokens. | The response is validated (dict, string email with `@`, string token of 16-4096 characters that is not digest-shaped). Anything else gets a 401 and writes nothing. |
| F5 | API4 | Unbounded bearer values were hashed and queried. | Bearers over 4096 characters are ignored. |

## Verified acceptable (no change)

- Password hashing is bcrypt with cost 12. Login is timing-safe for unknown users (`DUMMY_HASH`). Role and disabled state are re-read from the database on every request, so a demotion takes effect immediately.
- JWT algorithm is pinned (`HS256`), so `alg=none` and alg confusion are not possible. The secret must be at least 32 characters and is required when auth is enforced (`core.auth_security`). Mounted `_FILE` secrets are handled in PR #5774.
- `md5` uses in `backend/` are non-security: deterministic seeds, ETags and display ids.
- No `yaml.load`, `pickle.loads`, `shell=True` or `$where` was found in `backend/core` or `backend/routes`.
- Outbound HTTP in `routes/app_runtime.py` rejects credentials, query and fragment in URLs and disables redirects. The other internal probes target fixed loopback paths, not user-supplied URLs (no SSRF).

## Open findings (owner decision or follow-up)

| ID | OWASP | Finding | Recommendation |
|---|---|---|---|
| O1 | A01, API5 | No global authentication middleware. Authorization is per-router (`require_role`, `require_authenticated_identity`, LAFS operator gate). `core.route_policy_coverage` tracks a fail-closed route-policy rollout that is not yet complete. | Finish the route-policy rollout and enforce globally once `unwritten_routes == 0`. Until then, treat any router without a dependency as public. |
| O2 | A01 | `POST /api/prood/saga/deploy` has no auth dependency and writes to (and, on rollback, deletes from) `jeeves_vault`. | Gate it with `require_role("editor")`, or retire the demo endpoint. This changes a public contract, so the owner should decide. |
| O3 | API4 | `GET /api/prood/readiness` and `GET /api/gameforge/coverage/selftest` fan out to many internal HTTP probes per unauthenticated request (amplification). | Add a short-TTL cache with single-flight, or require auth. |
| O4 | A07 | `POST /api/auth/register` answers "Email already registered" (account enumeration). | Return a uniform response and notify by email, if the product accepts that UX change. |
| O5 | A07 | There is no per-account login throttling beyond the global IP rate limiter. | Add per-email attempt counters with backoff. The durable job and lease patterns in PR #5777 can back a shared counter. |
