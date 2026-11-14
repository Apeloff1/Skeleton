# Encrypted offline fair-stream result custody

The canonical fair-stream execution journal persists RUNNING before invoking
the model backend. The new `SealedFairStreamResultVault` implements its
`DurableResultBackend` protocol and commits an AES-256-GCM sealed output before
returning the ciphertext SHA-256 digest. The journal then publishes a signed
completion receipt. A process crash or exception at any point leaves the lease
non-retriable; an operator can reconcile only an already committed receipt.

## Application wiring

The trusted app opens **two different** private POSIX SQLite handles with
`open_private_sqlite`: one for custody/journal and a separate
`sealed-results.db` for encrypted output. It provisions a 32-byte result key
separately from custody, execution and recovery keys, and binds immutable
SHA-256 model and tokenizer identities. Instantiate the vault with an app-owned
synchronous `generate(permit, state) -> (consumed_tokens, bytes)` backend.
Pass `JournaledExecutionOwner(journal, vault)` as the
`OfflineAdaptiveDispatchService` execution owner. The service already
requires live CPU admission and an independent high-watermark. No network
provider or GPU qualification is implied.

The trusted app must authenticate the operator before retrieving results.
After validating the signed journal receipt and exact lease, call
`vault.read_committed(permit, expected_result_digest=receipt["result_digest"])`.
No result retrieval endpoint is exposed by this change. The app must not log
plaintext, raw prompts, keys or ciphertext. The vault rejects mismatched model,
tokenizer, session, generation, checkpoint, lease, request or receipt digest.

## Safety limits and release holds

Each output is at most 1 MiB, with 1,000 rows and 64 MiB of ciphertext at most.
The SQLite handle separately enforces a main database page cap. Disk reserves,
rollback journals, snapshots and encryption-key custody remain app obligations.
The caller must use a private, verified filesystem directory, never a shared
connection. Result encryption is not an external anti-rollback anchor; a
restored older SQLite snapshot cannot be accepted as a new custody generation.
Unknown telemetry remains conservative, and CPU-only execution does not imply
Metal, CUDA, ROCm, M-chip, battery or thermal device qualification.

Run `python -m pytest -q skeleton/testing/test_fair_stream_result_vault.py`
and the existing journal, dispatch and private SQLite regressions. Exact-head
security and integration checks are mandatory before promoting the draft.
