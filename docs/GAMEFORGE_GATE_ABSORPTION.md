# GameForge Gate Absorption

Status: durable audit, request bounds, verified principal credentials, fail-closed route-domain policy, strict static route inventory, rollout coverage accounting, and the existing JWT/RBAC surface now have Skeleton-native hardened contracts. Global HTTP policy enforcement remains staged; the API surface is fully inventoried and policy-written, while domain migration away from the explicit `legacy_api` bucket continues.

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

## Verified principal contract

`backend/core/principal_seal.py` provides a framework-neutral principal credential and route admission layer.

The v1 credential is:

```text
v1.key_id.principal_id.attester_id.issued_at.expires_at.signature_hex
```

Its invariants are intentionally stricter than the mined implementation:

1. HMAC-SHA256 covers the version, key id, principal, attester and both timestamps.
2. Verification selects one explicit key id instead of trialing every live secret.
3. Verification uses constant-time signature comparison.
4. Keys shorter than 32 bytes are rejected at configuration time.
5. Principal, attester and key identifiers are bounded and restricted to an unambiguous character set.
6. Credentials have issue and expiry timestamps, a local maximum TTL and bounded clock skew.
7. Unknown keys, malformed credentials, unsupported versions, excessive TTLs, future credentials, expired credentials and signature mismatches fail closed.
8. A keyring can retain old verification keys while issuance moves to a new key.
9. A codec without an explicit signing key is verification-only and cannot mint credentials.

## Static route inventory is now a hard quality boundary

`backend/scripts/backend_route_inventory_core.py` and the repository-aware `backend/scripts/backend_route_inventory.py` statically inventory the registered FastAPI surface without importing application modules or booting databases/providers.

The scanner understands:

- the canonical `core/routes_registry.py` registry;
- literal router/mount prefixes;
- local `include_router` composition;
- guarded direct router imports across modules;
- local router factories;
- imperative `add_api_route` calls;
- the fixed in-repo GameForge CNS dynamic subrouter manifest;
- recursion/cycle detection and explicit unresolved evidence for unsupported dynamic composition.

The first strict clean baseline measured:

- **217 / 217 registered route modules scanned**;
- **2,158 method+path registrations**;
- **2,114 unique paths**;
- **0 unresolved route expressions**;
- **0 duplicate method+path registrations**.

Before strict mode was enabled, the inventory exposed 16 duplicate registrations. Consolidation removed the obsolete static Hub/Compiler collisions, separated the build-pipeline vault compatibility surface, and eliminated the duplicate swarm `/census` registration by making `swarm_cold_legion.py` one canonical router.

`.github/workflows/backend-quality.yml` now runs the inventory with both `--strict` and `--fail-on-duplicates`, and `backend_route_collisions.py --fail` independently verifies that registration order cannot hide duplicate endpoints.

## Fail-closed route policy and measured rollout

`backend/core/route_policy_coverage.py` classifies unique application paths as explicit-open, domain-protected, or unwritten and can fail when coverage is incomplete.

`backend/core/route_policy_catalog.py` adds the canonical report-only catalog. Health/readiness remain narrowly prefix-open; login/register/session are exact-open only so future descendants cannot silently become public. Protected domains use longest-prefix classification, with `/api` as an explicit protected migration bucket named `legacy_api`.

On the clean baseline, `backend/scripts/backend_route_policy_report.py` measured complete written coverage and an enforcement-ready inventory. The first domain distribution included:

- `studio`: 248 paths;
- `gameforge`: 285;
- `jeeves`: 54;
- `worldforge`: 31;
- `learning`: 99;
- `vault`: 14;
- `governance`: 13;
- `build_artifacts`: 12;
- `code_execution`: 10;
- `collaboration`: 8;
- smaller operations/identity/tooling domains;
- `legacy_api`: 1,317 paths, approximately 62.7% of protected paths.

The inventory is therefore structurally ready for report-only admission, but domain migration is not finished. `legacy_api` is deliberately protected rather than open; its ratio is the measurable debt to reduce before broad enforcement.

## Existing JWT/RBAC surface hardened

Skeleton already had `backend/routes/gameforge_auth.py`, so the gate work strengthens that route rather than introducing a second login/session system.

`backend/core/auth_security.py` now owns security-sensitive configuration:

- production-like environments default to auth enforcement when no explicit override is provided;
- production token minting requires an explicitly configured strong JWT secret;
- local development without a configured secret gets a process-ephemeral secret instead of a public fixed fallback;
- bootstrap admin creation is disabled unless an email/password pair is explicitly supplied;
- bootstrap passwords are strength-bounded and excluded from object representation;
- the external OAuth/session exchange URL is validated and must use HTTPS when auth is enforced;
- diagnostics expose only non-secret configuration state.

`backend/routes/gameforge_auth.py` now uses PyJWT, verifies issuer/audience, issues JTI-tagged tokens, removes repository-default administrator credentials and public fallback secrets, and resolves the OAuth provider endpoint before network access.

Deployment note: removing repository defaults does not delete any historical administrator record that may already exist in a persistent database. Existing deployments should review/rotate legacy administrator credentials as part of rollout.

## Validation

The convergence/quality layers cover:

- principal seal issuance, tampering, TTL/skew and key rotation;
- route-domain admission and coverage accounting;
- exact-open bootstrap semantics;
- auth configuration and the real PyJWT route contract;
- recursive/static backend route inventory including CNS dynamic composition;
- duplicate collision evidence;
- inventory-backed route policy reporting;
- existing WORM audit, charter policy, deployment trust and execution evidence suites.

A strict route-baseline run passed Backend Quality, Product Convergence, Lint, Route Coverage and Deployment Trust together. CI/CD runs may be cancelled by newer pushes because this branch is receiving rapid consolidation commits; cancellation is not treated as a passing result.

## Rollout boundary

The principal/domain contract is still **not** installed globally as enforcing middleware. Structural inventory readiness is now proven, but broad authorization rollout should remain staged:

1. continue splitting `legacy_api` paths into narrower governance domains;
2. map sensitive domains into `CharterPolicy` / capability authorization;
3. add a FastAPI report-only adapter that verifies a principal seal and stores only `VerifiedPrincipal` on request state;
4. append allow/deny decisions to the existing durable WORM evidence boundary where required;
5. compare report-only decisions against legitimate traffic and eliminate policy mismatches;
6. enforce high-risk domains first;
7. reduce the allowed `legacy_api` ratio through CI over time;
8. only then consider broader default enforcement.

This keeps the useful GameForge doctrine—verified identity, explicit policy and fail-closed evidence—while avoiding a second gateway stack and unsafe big-bang enforcement.
