# Sealed Context Sandwich v1 — lossless *archive*, bounded live attention

**Status:** portable codec, canonical read bridge and adversarial conformance suite. Not yet production-bound to a transactional Mongo archive/outbox. The existing conversation authority remains `backend/core/conversations.py` (Mongo), with `skeleton/persistence/conversation_repository.py` as the SQLite conformance implementation. This addition lives in the existing `skeleton/context` owner, not a new service or memory authority.

## Scope and honest guarantees

The system supports exact byte recovery **of every event captured and retained by the archive**, with cryptographic tamper detection and a digest-linked sequence. This does **not** mean 100% of past tokens can enter a finite model context window, that anything never captured can be restored, that externally referenced attachments are already backed up, or that model internal/private reasoning and weights are available for export. A valid AES-GCM tag authenticates bytes within a frame; only an independently held, trusted head plus exact-next predecessor checks can establish chain completeness against a known committed sequence. Disaster recovery still requires durable writes, backup testing, KMS key continuity, and independent authority.

Do not claim 'zero knowledge': the backend decrypts context, the intended LLM provider might see selected material, and metadata (tenant/model/sequence/ciphertext length) remains visible. Do not claim milliseconds for NVMe/GPU KV restores without backend-specific measured end-to-end evidence. Encryption does not itself provide rollback prevention, lossless attention, or cross-backend KV tensor compatibility.

## Wire contract

`ContextSandwichCodec.seal(payload, binding, previous)` accepts raw bytes (up to 4 MiB each). AES-256-GCM encrypts `SHA256(payload) || payload`, with a fresh CSPRNG 96-bit nonce and `domain || canonical_header_json` as AAD. JSON serializes the top bread (`schema_version`, tenant, owner, conversation, sequence, previous commitment, key ID, model ID, policy ID, payload length) and the encrypted filling (`nonce`, `ciphertext || tag`). The next head is `SHA256(domain || exact_canonical_envelope_bytes)`, and the chain increments one event at a time. The AEAD provides a tag; additional HMAC over ciphertext is unnecessary. No plaintext content hash is released in public header metadata.

A separate `ContextEvent` stores source role/classification, event identity, provenance and the exact opaque content bytes. It is canonical JSON containing padded URL-safe base64 bytes; malformed, duplicate, noncanonical, oversized, or inconsistent input fails closed. A serialized `system` event is *not* an authorization to inject a system prompt: the canonical context compiler re-authorizes trust and instructions on every model call.

### Authoritative commit/replay lifecycle

1. Obtain authenticated `ContextBinding` and authoritative `ContextHead` from server-side conversation state, never client-supplied metadata. The genesis head is `(0, 000...000)` only for a never-published archive stream.
2. Ensure the source user/message is committed to the existing canonical conversation owner (including idempotency, branch lineage, privacy and quota checks). Build one context event for each immutable message. Include references for oversized content; separately archive referenced object bytes if full data recovery is needed.
3. `seal_event` returns ciphertext and a **candidate** next head. Persist ciphertext and CAS/fence the head under the same authoritative transaction / transactional outbox. If either part fails, do not acknowledge the archive publication as durable or advance a trusted head. Do not put plaintext or encryption keys in receipts/logs.
4. Offload ciphertext to an untrusted tier only after a durable publication receipt. On retrieval, validate authorization independently, replay every required frame in exact order, and compare the resulting commitment to the trusted, durable head. A client can return an old valid ciphertext+head pair; accepting its head as authority is a rollback vulnerability.
5. If old prefix data is archived in checkpoints, provide the anchored `starting_head` from the authoritative store. An untrusted checkpoint is not proof of completeness.
6. Restore raw bytes. For a provider call, pass through existing budget/trust-governed `skeleton/context/compiler.py`; if the caller explicitly requires *all* events live, refuse when they do not fit. A byte budget is not a tokenizer bound; the canonical compiler still enforces actual tokens and output reserves.

### Implemented bridge and limitations

`export_canonical_conversation` pages `list_messages` across the **entire** canonical conversation (all immutable branches, not merely the current active transcript). It checks exact-next message sequences and verifies the thread version did not move during export. Each message's `as_dict()` is deterministically encoded (exact `content` characters and all canonical message references/metadata, not the original DB physical encoding). `verify_export_against_canonical_conversation` re-reads the authorized source and compares it to decoded ciphertext, so a client-returned old valid export is not accepted when the canonical state changed. It uses a synchronous reader protocol matching the SQLite conformance interface; the async Mongo production adapter is a separate integration step.

These routines are **read-only export and verification**. They do not create a new authoritative store, do not bind a durable CAS head or outbox, and do not silently replace existing contextual compaction. They make no claim that `content_ref` and attachment object bytes have been copied; those are durable references that must be resolved and sealed under object-store consent, malware and retention policy.

## Mandatory operational controls for promotion

- **Keying:** backend-only KMS/HSM or protected secret provider; distinct tenant isolation; versioned key IDs; secure rotation with old-key decrypt interval; CSPRNG nonce generation and invocation-volume ceiling/rotation policy. Never put key material in client bundles, Git history, logs or traces. GCM nonce collisions have nonzero probability; no claim of mathematical impossibility.
- **Confidentiality:** classify policy/system context; redact restricted secrets before intentionally capturing; enforce export authorization; do not serialize inaccessible private model reasoning; preserve only policy-permitted tool traces; support retention, consent and cryptographic erasure.
- **Concurrency:** transactional authority CAS, exact-next sequence and stable source idempotency, recover interrupted publishes, forbid divergent ciphertext at same published sequence, and fence concurrent writers/retries.
- **Availability:** replication, checksummed backups, periodic end-to-end restore drills (including KMS recovery), corruption alarms, storage quota and streaming backpressure, object-store multipart chunk semantics, and explicit degraded-state reporting.
- **Economics:** incremental sealed frames avoid re-encrypting a growing full transcript on every turn; full historical context sent to an API still costs O(history tokens), unless a provider-supported persistent prefix cache actually reuses computations.
- **KV cache:** treat existing `skeleton/kv` namespace/leases as *derived acceleration only*. Never serialize a pointer and claim tensors were backed up. Only add encrypted tensor checkpointing after the selected engine exposes snapshot/restore, tensor shape/dtype/layout, layers, positional encoding, tokenizer, adapters, quantization, model-weights digest, version and device compatibility; validate deterministic logits tolerance and real GPU transfer timings. It is never the archive authority.
- **Evidence:** require unit/adversarial tests, architecture checks, exact-head CI, concurrent CAS tests, database crash recovery tests, tenant cross-over tests, chaos replay and measurable restore metrics before a production-ready declaration.

## Conformance

`python -m pytest skeleton/testing/test_sealed_sandwich.py -q` covers byte fidelity, randomization, tag tamper, metadata/key isolation, nonce/canonical encoding, gaps, duplicate/reordered frames, stale committed heads, trusted checkpoints, event duplication, model budget refusal, key rotation, paged canonical export, missing canonical messages and stale verification. Run the full required repository architecture gates from `AGENTS.md` after repository-level changes.
