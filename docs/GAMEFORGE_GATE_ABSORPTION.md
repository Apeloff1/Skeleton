# GameForge Gate Absorption

Status: durable audit, request bounds, verified principal credentials, fail-closed route-domain policy, rollout coverage accounting, and the existing JWT/RBAC surface now have Skeleton-native hardened contracts. Global HTTP policy enforcement remains staged until the live route inventory is explicitly chartered.

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

## Fail-closed route policy and rollout coverage

`RouteDomainPolicy` is a separate pure contract so rollout does not implicitly change the live FastAPI surface.

- health/readiness paths can be declared explicitly open;
- protected route prefixes map to governance domains;
- matching is path-segment aware, so `/api/studioevil` does not inherit `/api/studio`;
- longest-prefix matching allows narrower domains such as `/api/studio/admin` to override `/api/studio`;
- a written protected route without a verified principal returns a 401-style admission result;
- an unwritten route is sealed with a 404-style result;
- an admitted result carries only identity that already passed cryptographic verification;
- domain-specific action authorization remains downstream in `CharterPolicy` / capability policy rather than being duplicated here.

`backend/core/route_policy_coverage.py` makes rollout measurable before enforcement:

- unique application paths are classified as explicit-open, domain-protected, or unwritten;
- exact-match framework exclusions cannot hide an entire sensitive prefix;
- per-domain route counts and deterministic path evidence are emitted;
- an incomplete inventory can be promoted into a hard failure through `require_complete_route_policy`;
- global policy enforcement therefore has a testable prerequisite instead of a manual readiness claim.

## Existing JWT/RBAC surface hardened

Skeleton already had `backend/routes/gameforge_auth.py`, so the gate work now strengthens that route rather than introducing a second login/session system.

`backend/core/auth_security.py` now owns security-sensitive configuration:

- production-like environments default to auth enforcement when no explicit override is provided;
- production token minting requires an explicitly configured JWT secret of sufficient length;
- local development without a configured secret gets a process-ephemeral secret instead of a public fixed fallback;
- bootstrap admin creation is disabled unless an email/password pair is explicitly supplied;
- bootstrap passwords are strength-bounded and excluded from object representation;
- the external OAuth/session exchange URL is validated and must use HTTPS when auth is enforced;
- diagnostics expose only non-secret configuration state.

`backend/routes/gameforge_auth.py` was aligned with the repository's actual maintained dependency boundary:

- PyJWT is used instead of the removed `python-jose` dependency;
- tokens now carry and verify issuer, audience, issue/expiry timestamps and a unique JTI;
- configured bootstrap credentials replace repository-embedded defaults;
- deferred database imports remain boot-safe while security configuration fails closed in enforced environments;
- the OAuth session endpoint is resolved before the network call, preventing configuration failure from being confused with provider unavailability.

Deployment note: removing repository defaults does not delete any historical administrator record that may already exist in a persistent database. Existing deployments should review/rotate legacy administrator credentials as part of rollout.

## Validation

`backend/tests/test_principal_seal.py` covers principal issuance/verification, tampering, time windows, maximum TTL, rotation, weak/missing/unknown keys, malformed credentials, route boundaries and fail-closed protected/unwritten routes.

`backend/tests/test_route_policy_coverage.py` covers deterministic coverage accounting, exact-only exclusions, complete/incomplete readiness, bounded failure evidence and JSON-friendly coverage snapshots.

`backend/tests/test_auth_security.py` covers production/dev enforcement defaults, explicit flag parsing, secret requirements, ephemeral development secrets, opt-in bootstrap credentials, HTTPS session configuration and secret-free diagnostics.

`backend/tests/test_gameforge_auth_hardening.py` executes the actual FastAPI auth module with the production PyJWT/bcrypt stack to prove issuer/audience/JTI token semantics, wrong-audience rejection, disabled-by-default bootstrap creation, explicitly configured bootstrap creation and production fail-closed token minting.

All four suites are included in `.github/workflows/product-convergence.yml`; the workflow installs the focused production auth dependencies required to exercise the real route module. Earlier focused runs passed 15/15 principal tests and 21/21 combined principal/route-policy tests before the broader CI handoff.

## Rollout boundary

The principal/domain contract is deliberately **not** installed globally as middleware in this slice. Skeleton has a large legacy API surface, and fail-closed policy is safe only after every intended route is either explicitly open or assigned to a domain. Turning it on before that inventory exists would convert a security improvement into an availability regression.

The next safe rollout sequence is:

1. generate an explicit route inventory from the existing registered FastAPI routes;
2. classify every production route as open or domain-protected;
3. use `route_policy_coverage` to prove the inventory is complete;
4. map sensitive domains into `CharterPolicy` / capability authorization;
5. add a FastAPI adapter that verifies a principal seal and stores only `VerifiedPrincipal` on request state;
6. append allow/deny decisions to the existing durable WORM evidence boundary where required;
7. run the adapter in report-only mode and prove there are no unclassified legitimate requests;
8. move protected domains to enforcement incrementally rather than flipping the whole API at once.

This keeps the useful GameForge doctrine—verified identity, explicit policy and fail-closed evidence—while avoiding a second gateway stack and unsafe big-bang enforcement.
