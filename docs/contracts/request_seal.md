# Request Seal contract (`x-gf-seal`) — v1 (wire format frozen)

Owner: Internal Systems. Source of truth: `skeleton/api/hmac_seal.py`
(`mint_seal`, `verify_seal`, `require_seal`, `load_keyring`) and
`skeleton/api/middleware.py` (`RequestSealMiddleware`, installed by `install_gate`
inside `create_app`). This document describes existing behaviour; it does not
change the wire format.

## Headers

| Header | Direction | Meaning |
|---|---|---|
| `x-gf-seal` | request | Expiring HMAC bearer seal (credential). Required on every non-open route. |
| `x-request-id` | request + response | Correlation id. Echoed on the response; minted if absent, replaced if duplicated/invalid. Not a credential. |

Open routes (default open prefixes, e.g. `/health`, `/ready`) skip the credential
check but still get `x-request-id`.

## Seal formats

Two forms are accepted. Signature is lowercase hex HMAC-SHA256 (64 chars).

1. Legacy / #16 (3-part):
   `{attester}.{unix_expiry}.{hex(HMAC_SHA256(key, "{attester}|{unix_expiry}"))}`
   - Signing input uses a pipe `|` separator.
   - `attester` may contain `.` (parsed with right-split into 3 parts).
2. Principal (4-part, Gate PrincipalAuth):
   `{principal}.{attester}.{unix_expiry}.{hex(HMAC_SHA256(key, "{principal}.{attester}.{unix_expiry}"))}`
   - `principal` and `attester` must not contain `.`.

`unix_expiry` is an integer number of seconds since epoch (UTC). Verification
tries the legacy form first, then the principal form. The verified `attester`
is exposed to handlers as `request.state.attester`.

## Keys

- `GF_SEAL_SECRET` — primary UTF-8 secret. Used to mint; kid `default`.
- `GF_SEAL_KEYRING` — optional rotatable ring `kid=secret[,kid=secret...]`.
- Verify tries every key (primary first), constant-time comparison per key.
- Mint signs with the primary, else the first ring entry.

## Expiry / replay

- Default TTL: **300 s** (`DEFAULT_TTL_SECS`); `mint_seal(attester, ttl_secs=300, principal=None)`.
- Rejected when `now > unix_expiry`. **No clock-skew allowance.**
- No nonce: a seal is a bearer token reusable until expiry. Clients should mint
  per request (or per short window) and must treat seals as secrets.

## Errors

| Condition | Middleware (`RequestSealMiddleware`) | Dependency (`require_seal`) |
|---|---|---|
| No signing key configured | `503 {"error":"seal_unavailable"}` | `503 "seal unavailable"` |
| Missing / malformed / expired / bad signature | `401 {"error":"invalid_seal"}` | `401` (opaque) |

Failure reasons are deliberately opaque.

## Known gap (fixed in this PR, additive)

Before this PR `RequestSealMiddleware` gated the 503 check on `_resolve_secret()`
(primary `GF_SEAL_SECRET` only), so **keyring-only deployments (only
`GF_SEAL_KEYRING` set) returned 503** even though `verify_seal` and
`require_seal` accept ring keys. The middleware now returns 503 only when both
the primary secret and the keyring are empty (`load_keyring()` empty). Covered by
`skeleton/testing/test_request_seal_keyring_gate.py`.

## SDK guidance

Use the reference minting algorithm above (or `mint_seal` server-side for
internal callers). Send `x-gf-seal` and an `x-request-id` on every call; on 401
re-mint once; on 503 surface "seal unavailable" (server misconfiguration).

## App routes need BOTH seal and session

`/api/v1/projects*` (skeleton.projects.v1, mounted in `create_app`) sits behind
`install_gate`, so `x-gf-seal` is required first (fail-closed: missing/bad seal →
`401 {"error":"invalid_seal"}`, no key → `503 seal_unavailable`). The seal attests
the calling client/service. The handler then requires an end-user session,
`Authorization: Bearer <session token>`. A missing or invalid session returns
`401 {"error":{"type":"ProjectContractError","code":"PROJECT.UNAUTHENTICATED",...}}`.
actor_id and tenant_id come from the session on the server side, never from the body.
