# Dragon acquisition — independent Ed25519 rights review
**Authored:** 2026-10-12 UTC. **Branch:** \`feat/dragon-wisdom-review-20261010\`.

## Source-permission trust hardening
Controlled pilot mode now requires TWO separate protections for an individual approved source:
1. The canonical Dragon \`SourceCaptureGrant\`, revocable in the owner-bound permission ledger, signed by the local permission authority. It must be within its own TTL, bound to the exact source policy receipt, registry digest, owner and reviewer, and the owner pilot kill switch must remain enabled.
2. A separately verified \`IndependentRightsAttestation\`, signed with **Ed25519** by an external review principal. It contains exact source owner, URL, source ID, capture grant digest, policy receipt, evidence digest, reviewer, issuer and key identity, explicit permitted reference retention, issue time and expiry. This is checked with a configured **public key only**; no external signing secret is held by the Dragon.

\`DragonExternalRightsVerifier\` verifies the trusted issuer/key identity and Ed25519 signature over canonical JSON, demands the exact live grant scope, rejects modifications and caps the attestation at one hour and never beyond the grant's expiration. The independent signer must perform actual rights, terms, robots and provenance review before signing; this signature is an authenticating receipt **not a license in itself**.

\`DragonResearchPilot\` requires a trusted \`DragonExternalRightsVerifier\` in its constructor and an attestation in each preview or execution. \`acquire_canonical_technical_article\` validates the same external signature before robots, before every page request and again before captured text is retained. Revocation of the local grant, expiry of either proof, changed owner/source scope or invalid independent signature stops additional work. Without the independent verifier, pilot mode fails closed.

Both attestation and grant unambiguously prohibit neural training or permanent weight promotion. Rights for screenshots, videos, licensed game assets and software redistribution are not implied by permission for reference-text capture. Public signing keys must be installed from independently administered trust configuration; arbitrary source-site data must never be allowed to choose a trust key.

## Acceptance evidence
The expanded offline source-operations tests check exact independent signature verification, tampered rights/evidence digest rejection, wrong public key, expiry, missing/bad attestation denial **before any HTTP request**, and the existing grant-revocation/kill-switch checks. Only explicit tests can establish this code is passing. No production issuer, site-permission process or live crawl was provisioned in the development turn.
