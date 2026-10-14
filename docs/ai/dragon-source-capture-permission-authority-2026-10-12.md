# Dragon source-capture permission authority
**Implementation:** 2026-10-12 UTC
**Scope:** Explicit one-source reference capture permissions; not model training.

## Trust model

The research platform now has a separate `DragonSourcePermissionAuthority` instead of treating a URL in the 248-entry research atlas as permission to fetch or retain text. A short-lived `SourceCaptureGrant` is HMAC-SHA256-signed with a **distinct 256-bit issuer key**, bound to the canonical owner, source ID, exact HTTPS URL, registry digest, already completed policy-stage receipt, evidence hash, human reviewer identity, issuer/key identity, unique nonce, grant issue/expiry and the sole action `reference_capture`.

**Issuance requires an authenticated issuer** with independently performed reviewer identity, external rights, robots, site terms and reference-retention checks, plus a source whose canonical policy receipt is still current. The reviewed policy receipt's expiry caps the grant; the grant's own lifetime is at most one hour. Those checks must actually happen outside the module before the trusted issuer passes the required verification flags. A boolean, signature or SHA-256 hash **does not itself create rights**, identify a real human, validate remote terms, or authorize collecting personal data.

The issuer stores exact signed grants in an owner-scoped SQLite custody table, with a separate durable revocation register. Verification rechecks the stored signature, live expiry, owner/source identity, key identity, revocation, source registry and **current** policy receipt. A grant signed for an earlier policy becomes unusable after renewal or expiration.

`revoke` requires the privileged issuer, leaves a durable revocation entry and invalidates later `verify` calls. `audit` provides a bounded, read-only, signature-checked census that distinguishes live-scoped, expired, revoked and policy-superseded grants. This census makes zero network requests and cannot approve source claims or neural weights.

## Key controls and threat boundary

- The issuer key must be provisioned from a restricted runtime secret manager, **never** persisted in Git, frontend bundles, logs, crawler HTML or DB records. Rotate keys by moving workers to a new separately controlled issuer/key ID and retiring old issuance.
- Issue and revoke endpoints must **not** be exposed as browser-accessible commands; authorize callers through an actual organization identity provider, require independent site-terms review, and retain the underlying policy evidence under a separate custody system.
- The HMAC verifier necessarily knows the shared signing key, so only a sealed service may hold the authority. HMAC is not a public-key proof of reviewer identity or institutional independence. A public-key / identity-provider review attestation remains a production-hardening improvement.
- Grants are only valid in addition to the canonical policy review, signed Dragon nest, real OS idle telemetry, global resource admission, robots, SSRF and transport controls. A site requiring login or a restricted SDK is not made lawful to crawl by this module.
- The `reference_capture` action cannot be escalated into rights to train a model, reproduce a copyrighted work, or access proprietary console assets. Training scopes are explicitly false.

## Validation

Focused regressions cover refusal of unverified issuer/reviewer assertions, role-conflicted sign-off, TTL bounds, exact source/owner/signature scope, key mismatch, expiry, revocation, audit isolation and corruption, and refusal after the canonical policy expires. These are authored tests and must pass exact-head CI before deployment.

**Not activated:** No live site was contacted, and no external legal/rightsholder consent is attested by this repository commit. The source catalog remains discovery metadata until checked per destination.
