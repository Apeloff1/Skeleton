# Cooperative CPU + RAM + KV admission bundle

`LongContextAdmissionBundle` composes existing independently guarded CPU
capacity, process-local memory reservations, and generation-fenced KV/tokenizer
observations. It rejects cross-principal, cross-stream, model, tokenizer,
checkpoint, generation, and token-quantum mismatches before any reservation.

State machine: absent → reserved → claimed → released/revoked. The reserve
path checks KV identity and estimated RAM first, reserves memory second, then
CPU capacity, and only publishes a random bundle identity after all receipts
agree. A failure at any step releases both underlying reservations. Claim
re-observes KV, CPU head/pressure/disk, and RAM/principal; failure revokes the
entire bundle. Close revokes all. Forks fail closed before acquiring inherited
locks; process restarts cannot recover a stale in-memory reservation.

All receipts are payload-free and explicitly say they are **not** execution
leases, admission grants, device qualifications, RAM allocations, or
cross-process exclusive reservations. This coordinator does not implement GPU
or Apple Silicon qualification; unsupported device requests are rejected.
Backend execution still needs independent authorization, exact tokenizer and
model snapshot attestation, actual KV allocation, cross-process admission,
pressure/thermal checks, and durable proof of token consumption.

The coordinator is exported lazily from `skeleton.ai.model_runtime` for
app/service wiring. Its caller must provide trusted guard instances with
independent principal verifiers. No CLI path fabricates authorization.

Focused test: `python -m pytest -q tests/flgb/test_long_context_admission_bundle.py`.
Full exact-head CI and security validation remain release prerequisites.
