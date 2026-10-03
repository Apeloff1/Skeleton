# P3 Deferred Batch 01 — Multimodal and Governed Extensions

This batch materializes a contiguous slice of the frozen P3-T2 deferred frontier: **VOL-153 through VOL-163**. The P3-T2 execution map remains historical evidence and is not rewritten. This successor batch selects 11 of its 178 deferred volumes, leaving a projected 167-volume remainder for later governed batches.

## Scope

The multimodal side covers bounded media ingestion, media metadata, image-region provenance, document/OCR evidence, audio timing, explicit live-speech session state, bounded video sampling, and trust-filtered cross-modal retrieval. Resource, tenant, classification, trust and time constraints are applied before unsafe decode or ranking boundaries where applicable.

The extension side covers a schema-bearing Tool SDK, connector declarations and scoped sessions, plugin manifests/grants/lifecycle, and marketplace package attestation with quarantine and revocation. Tool declarations do not authorize themselves; connector credentials are represented by opaque handles; plugin grants cannot exceed declared permissions; marketplace verification is fail-closed.

## Authority boundary

This batch provides implementation, tests and evidence scaffolding only. It does **not**:
- mark any canonical masterplan volume complete;
- set implementation or verification signatures;
- promote a model, plugin, connector, or tool into production;
- weaken capability, security, sandbox, or merge-readiness gates;
- rewrite the frozen 19/178 P3-T2 ledger.

The reference marketplace verifier uses stdlib HMAC-SHA256 only as a deterministic test/reference attestation primitive. Production deployments can supply an asymmetric verifier behind the same package/attestation boundary.

## Machine contract

The successor projection is recorded in `machine/ai_p3_deferred_batch_01.json`. Its validator, `scripts/check_p3_deferred_batch_01.py`, proves that:
1. all 11 selected refs still belong to the exact 178-volume P3-T2 queue;
2. selected plus projected remaining volumes preserve the source queue exactly;
3. each selected volume has one owner;
4. all 33 canonical masterplan contract names are materialized;
5. no task self-completes or self-signs.

## Validation

Focused commands:

```bash
python scripts/check_p3_deferred_batch_01.py
python -m pytest -q tests/test_p3_deferred_batch_01.py skeleton/testing/test_p3_deferred_multimodal_tools.py
python -m compileall -q skeleton/ai/runtime/extensions
```

Generic repository CI remains the independent merge authority.
