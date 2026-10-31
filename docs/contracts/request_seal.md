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

## Seal v3 (request-bound, single-use, skew window)

Closes the remaining Jenkins #4594 finding: v2 binds a domain but not the
request, so a captured v2 seal could be re-pointed at a different method, path,
query, body or tenant within its domain before the nonce was consumed. v3 binds
all of them. v1/v2 are unchanged.

Wire (8 dot-separated fields, literal `v3` prefix):

```
v3.{principal}.{attester}.{domain}.{tenant}.{unix_ts}.{nonce}.{mac}
```

Canonical MAC input (UTF-8, `\n`-separated, version-tagged, 11 lines):

```
gf-seal/v3
{METHOD}            upper-case HTTP method
{canonical_path}    percent-decode once, re-encode all but unreserved (A-Z a-z 0-9 - . _ ~) and "/"
{canonical_query}   parse k=v pairs (blank values kept), RFC 3986-encode, sort, join with "&"; "" if none
{sha256(body)}      lowercase hex SHA-256 of the exact body bytes ("" body → e3b0c442…)
{principal}
{attester}
{domain}
{tenant}            value of x-gf-tenant, or "-" when the request has none
{unix_ts}           issue time, integer seconds (UTC)
{nonce}
```

`mac = lowercase hex(HMAC_SHA256(key, canonical))`, same keys/keyring as v1/v2.

- `tenant`: `-` or `[A-Za-z0-9_:-]{1,128}`. Sent as header `x-gf-tenant`; the
  server MACs over its own view of the header (absent → `-`), so adding,
  removing or changing it fails. More than one `x-gf-tenant` → 401. The verified
  tenant is exposed as `request.state.seal_tenant`.
- Timestamp: accepted iff `|now - unix_ts| <= SEAL_SKEW_SECS` (300 s).
- Nonce: `[A-Za-z0-9_-]{16,128}`, 128 random bits, one per seal. Recorded via
  the `NonceStore` port with scope `"seal"` and key `principal.attester.nonce`,
  retained for `SEAL_SKEW_SECS + REPLAY_SKEW_SECS` past `unix_ts`, so any replay
  that still passes the skew check is rejected.
- Body: `RequestSealMiddleware` buffers at most `MAX_SEALED_BODY_BYTES`
  (8 MiB) to hash, only for v3 seals, then replays the same bytes downstream.
  Larger → 401.
- Order: format → skew → MAC (all keys, `hmac.compare_digest`) → tenant and
  domain (`hmac.compare_digest`) → nonce record. Every failure is opaque 401
  `{"error":"invalid_seal"}`.
- `verify_seal(..., request=SealRequest(...), nonce_store=...)`. A v3 seal with
  no `request` is rejected. `require_seal` accepts a v3 seal only when
  `RequestSealMiddleware` already verified that exact header on the request.
- Any header starting `v3.` is parsed only as v3.

### Nonce store port (`skeleton/api/nonce_store.py`)

```python
class NonceStore(Protocol):
    def check_and_record(self, scope: str, nonce: str, ts: float, ttl_s: float) -> bool: ...
```

True means fresh, and the nonce is recorded until `ts + ttl_s`. False means replay
(or an invalid argument). `scope` namespaces callers (`"seal"`, `"s2s:<service>"`).
The default `InMemoryNonceStore` is thread-safe, bounded and **fail-closed**:

- **Sizing:** `max_entries` comes from `SKELETON_SEAL_NONCE_STORE_MAX`, default `100_000`.
  An invalid value (not a positive integer) raises at startup. Each entry lives for
  `ts + SEAL_SKEW_SECS + REPLAY_SKEW_SECS` (about 330 s by default). Size the store above
  the peak number of v3 seals verified per process in that window, with headroom.
  For example, 200 req/s × 330 s ≈ 66 000.
- **Full store:** expired entries are reclaimed first. If every entry is still live,
  the new seal is **refused** and nothing is evicted. Live nonces are never dropped,
  so a full store can't reopen a replay window. There is no LRU mode.
- **Signalling:** `check_and_record` keeps its signature. On a full store it **raises
  `skeleton.api.nonce_store.NonceStoreFull`** (with `retry_after_s`, at least 1, equal to the
  seconds until the soonest entry expires) rather than returning a value. `verify_seal`
  lets `NonceStoreFull` propagate. Any other store exception still becomes an opaque
  `AuthError`. `RequestSealMiddleware` answers
  `503 {"error":"nonce_store_full"}` with `Retry-After: <retry_after_s>`. Clients should
  back off and re-seal, because each retry needs a fresh nonce.
- **Metrics:** each refusal increments `store.nonce_store_full`, which `store.stats()`
  returns along with `entries`, `max_entries` and `reclaimed`. If the store is built with
  `metrics=` (any object with `increment(name, value, labels)`, such as
  `skeleton.observability.metrics.MetricsCollector`), it also emits the counter
  `nonce_store_full{scope=...}`. Alert on any non-zero rate.

Shared stores (e.g. Redis) must keep the same contract: raise `NonceStoreFull` when they
can't record, and never evict live nonces.
Multi-replica deployments pass a shared store, for example
`RequestSealMiddleware(app, nonce_store=...)` backed by Redis `SET NX EXAT`.

### Mint

- Server: `hmac_seal.mint_seal_v3(attester, domain, method=, path=, query=, body=, tenant=)`.
- SDK: `skeleton.client.seal.mint_request_seal_token(...)`, which produces the same bytes (parity-tested).
  `RequestSealer(..., domain=, bind_request=True, tenant=)` /
  `GatewayClient(seal_domain=, seal_bind_request=True, seal_tenant=)` build the
  httpx request first and seal the exact method, path, query and body bytes that
  are sent, with a fresh nonce on every request and on every retry.

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
| v3 method/path/query/body/tenant mismatch, timestamp outside skew, replayed nonce, body > 8 MiB, duplicate tenant header | `401 {"error":"invalid_seal"}` | `401` unless middleware verified it |
| v3 seal valid, but nonce store full of live nonces | `503 {"error":"nonce_store_full"}` + `Retry-After` | n/a (raises `NonceStoreFull`) |
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
