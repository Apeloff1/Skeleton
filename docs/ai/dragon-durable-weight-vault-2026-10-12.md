# Milestone — durable signed Jeeves weight deployment and restart-safe rollback

**Timestamp:** 2026-10-12 UTC · **PR:** #3605 · **Branch:** `feat/dragon-wisdom-review-20261010`

## What was actually added

`DragonDurableWeightVault` is a tenant-scoped SQLite custody store for Jeeves **application retrieval indexes**, not mutable neural-model weights. Each activation requires the complete independently signed 100-matrix report, signed cross-source factual corroboration, signed holdout evaluation, and independent signed operator approval; it delegates validation to the existing `JeevesWeightOverlay.activate()` before recording a generation. It uses a SQLite `BEGIN IMMEDIATE` compare-and-swap transaction so concurrent writers cannot publish with an obsolete generation.

The immutable journal retains bounded index entries, SHA-256 event digests, previous-event linkage, prior/current index identities, evaluation/matrix/approval custody digests, expiry, action and observed time. A separately provisioned 32-byte-or-longer HMAC signing key seals every event and the owner-scoped head record. Reconstruction always checks the full event chain, sequence continuity, canonical JSON and index digest. Tampering with a previously committed event, head, index or sequence fails closed. Validating a chain is bounded to 512 events and 512 entries/generation; serving indexes incurs custody replay work and is not claimed to be constant-time.

## Why this changes the deployment

Previously, `JeevesWeightOverlay` kept only in-memory `_generation`, `_active`, `_postings` and at most four previous generations. A process restart lost active index and rollback history. The new vault rehydrates from verified SQLite custody, rejects stale activations, and returns owner-scoped, read-only retrieval routes for authenticated, unexpired generations. It cannot issue crawler rights, approve facts by itself, or alter neural model parameters.

The signed rollback order includes the tenant, exact current index digest, previous approved index digest, expected generation, independent operator/key ID, issuance and expiry, and a reason digest. Rollback is itself appended as another immutable, HMAC-sealed event; it does not delete the failed version or silently reset generation counters. A rollback target must still have unexpired authorization. There is no automatic rollback from arbitrary browser input.

## Regression gates

The Dragon hyperweight regression suite adds restart from a real SQLite file, consecutive shadow→weight and weight→hyper releases, retrieval after restart, signed rollback to an earlier index, stale generation refusal, expired serving refusal, missing or mismatched operator key rejection, incomplete signed matrix rejection, per-owner isolation, event tampering detection and verification of a historically rewritten record.

## Security and limits

A journal HMAC protects against untrusted database edits **provided the separate signing key remains secret**. It does not protect against a fully compromised app or compromised signer. Existing fact-review and benchmark signatures remain required on every new promotion. The retrieved content itself is still governed by its original source licenses. The vault is an opt-in service component and is not automatically deployed until a trusted operator provisions its dedicated database and signing key.

**2026-10-12 UTC improvements:** (persistent index generations across restart); (strict signed promotion and rollback custody); (historical tamper detection); (expiry and tenant separation enforced during retrieval).
