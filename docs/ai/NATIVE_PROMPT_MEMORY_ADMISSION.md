# Bounded native prompt-memory admission

The CPU-only offline fair-stream application stages original prompt text in RAM
before the durable execution journal claims its lease. This feature adds a
separate, explicit **RAM budget for staged plaintext**; it is not a KV reservation
or a GPU/M-chip device qualification. A staged prompt is charged by its strict
UTF-8 byte length. The registry uses a single lock for reservation and grant
publication, consumption and release, and irreversible revocation.

Defaults: 4 MiB staged globally, 1 MiB per tenant, and 16 outstanding staged
prompts per tenant, within the existing global lifetime cap of 256 identities.
All caps are operator-configurable only within hard upper bounds. Failure to
reserve does not stage a grant. A wrong-tenant claim does not consume or free
another tenant's bytes. Consumed and revoked grants release ephemeral RAM
accounting but **never** restore a used request identity. A crash loses all
staged plaintext and grants; the durable execution journal remains the only
cross-restart one-use execution fence. No automatic replay or recreation.

The registry's `budget_status()` returns counts and byte totals without
prompt contents, request IDs, tenant IDs, token IDs or keys. The application
must still authenticate tenants before staging and use the canonical session,
journal, private result vault and live pressure guard for actual execution.
Unknown hardware telemetry continues to hold admission conservatively.

Focused regression command (not yet executed):
`python -m pytest -q skeleton/testing/test_native_prompt_budget.py skeleton/testing/test_native_fair_stream_backend.py skeleton/testing/test_offline_native_fair_stream.py`

## Authenticated app submission

`submit_authenticated_native_cpu_prompt` accepts the app-verified tenant
principal, canonical stream request and the exact bound service/vault/native
runtime/registry. It rejects a mismatched tenant, output cap or owner chain
before staging plaintext. On any durable submission exception it revokes the
in-memory grant and burns the request ID; a potentially committed durable
request is not replayed automatically. Only a successful canonical submit
leaves a staged prompt for the one-use execution journal.
