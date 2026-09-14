# GameForge Gate Absorption

Status: durable audit, request bounds, verified principal credentials and fail-closed route-domain policy now have Skeleton-native primitives. Global HTTP enforcement remains intentionally staged until the live route inventory is explicitly chartered.

## Source provenance

The source behavior was mined selectively from `Apeloff1/gameforge-middleware` rather than importing its ASP.NET/YARP application stack. The useful source concepts are concentrated in:

- `src/Zaibatsu.Gate/Auth/PrincipalAuth.cs` — signed, expiring principal identity plus explicit route-domain policy;
- `src/Zaibatsu.Gate/Middleware/GateMiddleware.cs` — request correlation, request-body bounds, durable-audit-before-service and fail-closed protected-route admission.

Skeleton preserves the source repository and promotes behavior into existing Python security/governance primitives.

## Existing Skeleton primitives retained

Skeleton already had stronger native equivalents for two gate responsibilities, so they were **not** duplicated:

- `backend/middleware/security.py::SizeLimitMiddleware` bounds mutating API request bodies;
- `backend/core/worm_audit.py::WormAuditLog` provides append-only hash ancestry, cross-process serialization, fsync-before-return, complete-chain verification, verified health state and fail-closed tamper detection.

The in-memory audit middleware remains useful for operational telemetry, while the WORM ledger is the durable evidence boundary.

## Newly promoted principal contract

`backend/core/principal_seal.py` adds a framework-neutral principal credential and route admission layer.

### Credential invariants

The v1 credential is:

```text
v1.key_id.principal_id.attester_id.issued_at.expires_at.signature_hex
```

Its contract is intentionally stricter than the mined implementation:

1. HMAC-SHA256 covers the version, key id, principal, attester and both timestamps.
2. Verification selects one explicit key id instead of trialing every live secret.
3. Verification uses constant-time signature comparison.
4. Keys shorter than 32 bytes are rejected at configuration time.
5. Principal, attester and key identifiers are bounded and restricted to an unambiguous character set.
6. Credentials have both issue and expiry timestamps, a local maximum TTL and bounded clock skew.
7. Unknown keys, malformed credentials, unsupported versions, excessive TTLs, future credentials, expired credentials and signature mismatches all fail closed.
8. A keyring can retain old verification keys while issuance moves to a new key, enabling rotation without accepting self-declared identity.
9. A codec without an explicit signing key is verification-only and cannot mint credentials.

## Fail-closed route policy

`RouteDomainPolicy` is a separate pure contract so rollout does not implicitly change the live FastAPI surface.

- health/readiness paths can be declared explicitly open;
- protected route prefixes map to governance domains;
- matching is path-segment aware, so `/api/studioevil` does not inherit `/api/studio`;
- longest-prefix matching allows narrower domains such as `/api/studio/admin` to override `/api/studio`;
- a written protected route without a verified principal returns a 401-style admission result;
- an unwritten route is sealed with a 404-style result;
- an admitted result carries only identity that already passed cryptographic verification;
- domain-specific action authorization remains downstream in `CharterPolicy` / capability policy rather than being duplicated here.

## Validation

`backend/tests/test_principal_seal.py` covers:

- issuance/verification round trips;
- signature coverage of key id and identity fields;
- principal/expiry tampering;
- expiry and not-yet-valid windows;
- verifier-side maximum TTL enforcement even for an otherwise valid HMAC;
- live-key rotation and verification-only operation;
- weak/missing/unknown key rejection;
- malformed identifiers and credentials;
- explicit open-route boundaries;
- segment-aware and longest-prefix route matching;
- protected-route identity requirements;
- fail-closed unwritten routes.

The suite is included in `.github/workflows/product-convergence.yml`. A focused local execution during absorption passed 15/15 tests before CI handoff.

## Rollout boundary

The principal contract is deliberately **not** installed globally as middleware in this slice. Skeleton has a large legacy API surface, and fail-closed policy is safe only after every intended route is either explicitly open or assigned to a domain. Turning it on before that inventory exists would convert a security improvement into an availability regression.

The next safe rollout sequence is:

1. generate an explicit route inventory from the existing route registry;
2. classify every production route as open or domain-protected;
3. map sensitive domains into `CharterPolicy` / capability authorization;
4. add a FastAPI adapter that verifies a principal seal and stores only `VerifiedPrincipal` on request state;
5. append allow/deny decisions to the existing durable WORM evidence boundary where required;
6. run the adapter in report-only mode and prove there are no unclassified legitimate requests;
7. move protected domains to enforcement incrementally rather than flipping the whole API at once.

This keeps the useful GameForge doctrine—verified identity, explicit policy and fail-closed evidence—while avoiding a second gateway stack and avoiding unsafe big-bang enforcement.
