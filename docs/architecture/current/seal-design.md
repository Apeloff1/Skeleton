# Seal design (`x-gf-seal`) and known gaps

Source: `skeleton/api/hmac_seal.py`, applied by `RequestSealMiddleware` inside `install_gate`.

## Wire format

- Legacy #16 (3-part): `{attester}.{unix_expiry}.{hex_hmac_sha256(attester|expiry, secret)}`
- PrincipalAuth (4-part): `{principal}.{attester}.{unix_expiry}.{hex_hmac_sha256(principal.attester.expiry, key)}`.
  The principal and attester must not contain `.`.

## Keys

`GF_SEAL_SECRET` is the primary key, used for both minting and verifying. `GF_SEAL_KEYRING` is an
optional `kid=secret,...` ring. Verification tries the primary key and then every ring key,
comparing in constant time. `mint_seal` uses `DEFAULT_TTL_SECS` = 300.

## Failure modes (fail closed)

- No secret and no keyring: **503** `seal_unavailable`.
- Missing, malformed, expired or bad signature: **401** `invalid_seal` (opaque).
- Open prefixes (`GatePolicy.is_open_route`) skip the credential seal. The correlation seal
  (`X-Request-Id`) is always set.
- The verified principal feeds `request.state` (see `AuthMiddleware`), never self-declared JSON.
  The realtime and projects layers authorise on top of it.

## Known gaps

1. **No request binding.** The MAC covers only principal, attester and expiry. It doesn't cover
   method, path, body hash or query, so a captured seal works on *any* sealed route until it
   expires.
2. **No replay protection.** There's no nonce or jti store, so a seal can be reused freely within
   its TTL (300 s by default, and longer if the minter chooses).
3. **The legacy 3-part form is still accepted.** It carries no principal, so a principal must come
   from elsewhere, which weakens attribution.
4. **Keyring entries are not scoped.** Any ring key verifies any attester, and kid isn't part of
   the wire format. There is no way to revoke one attester without rotating everyone's key.
5. **The engine prefix is outside the seal.** `/api/v1/engine` relies only on its own bearer
   token and principal validation.
6. **Mint TTL is caller-chosen.** `_require_ttl_secs` validates the type, but verify enforces no
   maximum, so a long-lived seal is valid if it's signed.

## References

- `skeleton.api.hmac_seal:mint_seal`
- `skeleton.api.hmac_seal:verify_seal`
- `skeleton.api.hmac_seal:require_seal`
- `skeleton.api.hmac_seal:load_keyring`
- `skeleton.api.hmac_seal:DEFAULT_TTL_SECS`
- `skeleton.api.middleware:RequestSealMiddleware`
- `skeleton.api.middleware:AuthMiddleware`
- `skeleton.api.middleware:GatePolicy`
