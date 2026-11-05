# Request Seal contract (`x-gf-seal`) — v1 (frozen) + v2 (domain-bound, single-use)

Owner: Internal Systems. Source of truth: `skeleton/api/hmac_seal.py`
(`mint_seal`, `verify_seal`, `require_seal`, `load_keyring`) and
`skeleton/api/middleware.py` (`RequestSealMiddleware`, installed by `install_gate`
inside `create_app`). v1 forms below are unchanged; v2 (see "Seal v2") adds
domain binding and nonce replay protection (Jenkins seal finding: v1 seals had
no domain binding and could be replayed until expiry).

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

## Seal v2 (domain-bound, single-use)

Wire (7 dot-separated fields, literal `v2` prefix):

```
v2.{principal}.{attester}.{domain}.{unix_expiry}.{nonce}.{mac}
```

Canonical MAC input (UTF-8, `\n`-separated, version-tagged):

```
gf-seal/v2\n{principal}\n{attester}\n{domain}\n{unix_expiry}\n{nonce}
```

`mac = lowercase hex(HMAC_SHA256(key, canonical))` (64 chars), same keys as v1.

- `principal`, `attester`, `domain`: `[A-Za-z0-9_:-]{1,128}` (no `.`).
  `principal` defaults to `attester` when minting.
- `domain`: the GatePolicy domain of the target route (`projects`, `realtime`,
  `agents`, `forge`, ...; longest-prefix match on the path). `RequestSealMiddleware`
  resolves the request's domain from GatePolicy and rejects any seal naming a
  different domain. A v2 seal on an unchartered path is rejected.
- `nonce`: `[A-Za-z0-9_-]{16,128}`; mint 128 random bits (`secrets.token_hex(16)`).
  Single use: the middleware records `(principal, attester, nonce)` in a replay
  cache and rejects any repeat.
- `unix_expiry`: `now <= expiry` (no acceptance skew, as v1) and
  `expiry <= now + 3600 + 30` (`MAX_V2_TTL_SECS` + `REPLAY_SKEW_SECS`) so cache
  lifetime is bounded. Default TTL stays 300 s.
- Any header starting `v2.` is parsed only as v2 (never falls back to v1), so
  v1 attesters must not start with `v2.`.

Replay cache (`skeleton.api.hmac_seal.ReplayCache` port,
`check_and_store(key, expires_at, now) -> bool`):

- Default `InMemoryReplayCache` (per process, thread-safe, bounded at 100 000
  live entries). Entries are kept until `expiry + REPLAY_SKEW_SECS` (30 s) to
  absorb clock drift between replicas. When full after purging expired
  entries it fails closed (401) rather than evicting live nonces.
- Multi-replica deployments must pass a shared store
  (`install_gate(app, replay_cache=...)`, e.g. Redis `SET key 1 NX EXAT expires_at`);
  a per-process cache only stops replays against the same process.
- `require_seal` (dependency) checks MAC, expiry and well-formedness only; it
  does not consume the nonce (the middleware already did on gated routes).

Mint: `mint_seal(attester, ttl_secs, *, domain="projects", principal=..., secret=...)`
(server) or `skeleton.client.seal.mint_seal_token(..., domain=...)` (SDK).

### Legacy (v1) policy: `GF_SEAL_LEGACY`

| Value | v1 3/4-part seals |
|---|---|
| `sensitive` (**default**) | accepted everywhere except `SENSITIVE_DOMAINS` = `{realtime}` |
| `allow` | accepted on every domain (rollback switch) |
| `deny` | rejected everywhere (target end state) |
| anything else | treated as `deny` (fail closed) |

Why `sensitive` by default: realtime streams carry other principals'
build/agent events (S1-1) and long-lived connections are the most valuable
replay target, and its only first-party minter (the realtime SDK test harness /
`RealtimeClient` header callable) already re-mints per connect, so moving it to
v2 breaks nothing. Every other surface keeps accepting v1 until the SDK and
service callers mint v2, so this ships without an outage; flip to `deny` once
v1 traffic is gone.

## Keys

- `GF_SEAL_SECRET` — primary UTF-8 secret. Used to mint; kid `default`.
- `GF_SEAL_KEYRING` — optional rotatable ring `kid=secret[,kid=secret...]`.
- Verify tries every key (primary first), constant-time comparison per key.
- Mint signs with the primary, else the first ring entry.

## Expiry / replay

- Default TTL: **300 s** (`DEFAULT_TTL_SECS`); `mint_seal(attester, ttl_secs=300, principal=None)`.
- Rejected when `now > unix_expiry`. **No clock-skew allowance.**
- v1: no nonce, reusable until expiry (bearer token). Treat as secret.
- v2: single use (nonce replay cache); mint one per request.

## Errors

| Condition | Middleware (`RequestSealMiddleware`) | Dependency (`require_seal`) |
|---|---|---|
| No signing key configured | `503 {"error":"seal_unavailable"}` | `503 "seal unavailable"` |
| Missing / malformed / expired / bad signature | `401 {"error":"invalid_seal"}` | `401` (opaque) |
| v2 domain mismatch, replayed nonce, missing/bad nonce, expiry too far out, replay cache full | `401 {"error":"invalid_seal"}` | `401` (MAC/expiry/format only) |
| v1 seal on a domain refused by `GF_SEAL_LEGACY` | `401 {"error":"invalid_seal"}` | n/a |

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

Python SDK (`skeleton.client`): `RequestSealer(..., domain="projects")` /
`GatewayClient(seal_attester=..., seal_domain="projects")` mint a fresh v2 seal
on every request (never cached, since nonces are single-use); retries call the
sealer again. A gateway talking to several domains needs one sealer per domain.
Realtime callers pass a header callable that mints with `domain="realtime"` per
connect. Without `domain=` the SDK still mints v1 (unchanged).

## Migration (v1 → v2)

1. Server ships v2 verify with `GF_SEAL_LEGACY=sensitive` (this PR): realtime
   requires v2, other domains accept both.
2. SDKs and service callers set a domain (`seal_domain=` / `domain=`).
3. Multi-replica deploys wire a shared `ReplayCache`.
4. Flip `GF_SEAL_LEGACY=deny`; later remove v1 verify.
Rollback: `GF_SEAL_LEGACY=allow`.

## App routes need BOTH seal and session

`/api/v1/projects*` (skeleton.projects.v1, mounted in `create_app`) sits behind
`install_gate`, so `x-gf-seal` is required first (fail-closed: missing/bad seal →
`401 {"error":"invalid_seal"}`, no key → `503 seal_unavailable`). The seal attests
the calling client/service. The handler then requires an end-user session,
`Authorization: Bearer <session token>`. A missing or invalid session returns
`401 {"error":{"type":"ProjectContractError","code":"PROJECT.UNAUTHENTICATED",...}}`.
actor_id and tenant_id come from the session on the server side, never from the body.
