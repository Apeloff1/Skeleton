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


## Phase 2: incremental Mongo-shaped streaming and binary attachments (2026-10-27)

The async bridge in `skeleton/context/sealed_conversation_async.py` accepts
the existing `MongoConversationAuthority.get_thread/list_messages` interface
without introducing a new owner. `iter_canonical_events_async`:

1. Reads the authorized thread ID, version and message-sequence high-water mark.
2. Emits an encrypted candidate thread checkpoint.
3. Pages **all** immutable messages in blocks of at most 500, including
   superseded and inactive-branch records, not only the visible transcript.
4. Enforces strictly contiguous sequence numbering and the original thread ID;
   missing rows and crossing a tenant/owner scope fail closed.
5. Re-reads the canonical thread after the final message. A moved version or
   changed snapshot rejects staging, even if earlier frames were sealed.

`stage_canonical_conversation_async` writes encrypted candidate frames to an
`AsyncFrameStagingSink` using begin/append/complete/abort. The sink must be
private, idempotently abortable, quota-limited and inaccessible to readers until
a **separate authoritative commit** succeeds. On an export exception, the sink
is aborted. The returned `StagedContextReceipt` is NOT proof of a committed
archive; it reports candidate head, canonical thread version, message count,
and emitted ciphertext-byte count. Under no circumstances should a client
return its own receipt and thereby establish a current trusted head.

`verify_staged_conversation_async` independently refetches canonical Mongo
messages and decrypts supplied frames one at a time. It checks the complete
canonical byte representation, authenticated sequence chain, tenant/model/policy,
end-of-stream, source version, message count, candidate head and ciphertext
count. Its expected version comes from an independently authorized Mongo read;
a matching old client-held archive is rejected if canonical state changed.
Because the source is read twice, object references and mutable external
artifacts still need **their own** versioned custody and retrieval controls.

### Chunked binary object format

`skeleton/context/sealed_blobs.py` can stage content bytes behind attachment,
tool-result or artifact references. It never writes plaintext into a public
header. `seal_blob_frames` incrementally reads up to 256 KiB per chunk;
each chunk uses `ContextEvent` with exact opaque bytes, canonical object ID,
exact-next frame sequence, encrypted origin binding and AES-GCM. A final
encrypted `receipt` event includes the object ID, total bytes, number of
chunks, protocol version, and SHA-256 of the complete plaintext object.

`restore_blob_to_staging` verifies all chunk indices, object identity,
authenticated frame links, terminal receipt and **externally trusted** final
head while streaming to a disposable output writer. The caller MUST discard
this writer on ANY exception. The output MUST NOT be published to a user or
tool before the function returns successfully. The wrapper
`restore_blob_bytes` is intentionally capped at 256 KiB for in-memory use.
Sources exceeding the explicit 8 GiB maximum fail, not silently truncate.
Storage quotas and object lifecycle/retention obligations remain with their
canonical owners.

These object frames are only **encrypted candidate payloads**. No attachment
is silently considered backed up merely because `content_ref` appears in a
conversation message. A production adapter must resolve references through
authorization, verify classification/consent, stage actual bytes, and commit an
immutable object-version identity and archive head together with a durable
publication receipt. A reference that cannot be resolved is an **incomplete
archive**, not evidence of zero loss.

### Required integration transaction (still pending)

The authoritative conversation owner must expose a transaction/CAS operation
scoped by tenant, owner, thread, source version and archive generation:

- Validate the source message/snapshot version and authorization.
- Verify frame count, object manifests, ciphertext existence, storage quota,
  referenced object versions, retention rules and key availability.
- Atomically fence the expected previous trusted head and record the next
  commitment / durable outbox publication under the *existing* Mongo owner.
- Mark a generation readable only when its entire encrypted payload is durable
  and verified; otherwise keep it uncommitted and retry or discard staging.
- On restart, reconcile unresolved outbox intents idempotently and fail closed
  on missing frames, missing keys, mismatched heads or revoked permissions.
- Support key rotation, legal deletion/crypto-erasure and owner-scoped export
  without creating a second conversation authority.

Do not claim operational zero-loss, authoritative replay resistance or
production recovery until that transaction and its crash/rollback/replication
tests land, are verified against live Mongo and pass exact-head CI.

### Targeted conformance additions

```bash
python -m pytest -q \
  skeleton/testing/test_sealed_sandwich.py \
  skeleton/testing/test_sealed_conversation_async.py \
  skeleton/testing/test_sealed_blobs.py
```

The added async suite checks multi-page (1,105-message) Unicode export,
independent matching recovery, drift, storage-failure abort, stale archive,
missing/extra frames and tenant mismatch. Binary tests check byte-exact
streaming for NUL/non-UTF8/Unicode payloads, empty objects, digest-bearing
terminal frames, wrong object IDs, duplication/reordering, truncation,
stale trusted head, write failures and size-budget refusal.

## Phase 4: canonical SQLite CAS conformance and correlated replay (2026-10-27)

The isolated `skeleton/persistence/sealed_memento_repository.py` module
adds SQLite **conformance** behavior, not another conversation authority.
It receives the already-open `SQLiteConversationRepository`, reuses its
connection and reentrant lock, and stores encrypted candidate frames
in two tables with foreign keys cascading from `conversation_thread`:

- `conversation_memento_head`: one authorized, policy/model-bound,
  independently fetched catalog head per conversation, including current
  source thread version. No plaintext history or encryption keys stored.
- `conversation_memento_frame`: monotonic global serial, cryptographic
  stream name, ciphertext frame and end-of-frame catalog checkpoint.

`publish` starts `BEGIN IMMEDIATE`, validates tenant/owner authorization,
writable conversation state, expected canonical thread version, exact
previous head, authenticated encryption, exact-next global/per-stream
sequence, trusted work receipt, and SQL existence of any causal predecessor.
It inserts the encrypted frame and advances the catalog head *in the same
SQLite transaction*. A stale head, source version change, missing causal
record, failed proof, authorization error or write failure rolls back both.
This blocks acceptance of an old client-held state even when its own
cryptographic authentication is valid.

`read_window` reads a single database snapshot. It independently obtains
the trusted head, checks an authenticated resume checkpoint, enforces a
2,000-event record limit **and 16 MiB ciphertext limit**, checks complete
global sequence continuity, re-verifies each frame's AEAD/stream chain and
all delivered-work proofs, and compares the final head to the trusted
catalog. It returns an explicit `has_more` cursor. It never returns a
truncated page as a complete archive. A revoked/expired work receipt now
fails read/replay rather than being presented as a completed execution.

`SealedMementoArchive.verify_append` verifies an incoming encrypted
candidate with the prior authorized catalog head; the archive's replay path
also rechecks execution receipts rather than trusting the fact that a work
event was sealed earlier.

`correlate_causal_bundle` expands authenticated lexical matches to
verified causal ancestors and descendants through serial IDs across all
three streams. It preserves original role labels and does not equate
LLM assertions with executed work. If a complete causal closure exceeds
the configured output budget, it refuses rather than silently hiding
related events.

### Known hard boundaries

1. **Production Mongo has not been wired.** Live Jeeves chat persists in
   `backend/core/conversations.py`; the SQLite adapter is the existing
   portable conformance harness. No production service is started here.
2. **External rollback witness is still required** for adversarial
   restoration of a database snapshot and all its trusted heads. AES-GCM
   proves ciphertext integrity, not freshness relative to a head copied
   from the same untrusted backup. Production should anchor/attest the
   head or use a separately governed monotonic authority.
3. **No claim of atomic remote object-store durability.** Metadata and
   ciphertext must be staged, replicated, verified and durably committed
   before a production Mongo majority-acknowledged publication advances
   the readable catalog. Crash, retry, failover and key-unavailable behavior
   must have a recovery outbox.
4. **No effective doubling of physical model tokens.** Three archives
   preserve separate provenance; retrieval is a bounded projection
   into a model's unchanged finite tokenizer/context-window limits.
5. **Retention and erasure must cascade.** SQLite foreign-key deletion
   removes associated candidate frames. Live production additionally
   needs legal retention hooks, KMS crypto-erasure, artifact reference
   deletion, audit receipts and backup expiry.

### Acceptance commands

```bash
python -m pytest -q \
  skeleton/testing/test_sealed_sandwich.py \
  skeleton/testing/test_sealed_conversation_async.py \
  skeleton/testing/test_sealed_blobs.py \
  skeleton/testing/test_sealed_memento.py \
  skeleton/testing/test_pre_delivery_guard.py \
  skeleton/testing/test_sealed_memento_repository.py

python scripts/check_architecture_map.py
python scripts/check_ai_app_construction.py
python scripts/check_capability_interfaces.py
python scripts/check_provider_bootstrap.py
python scripts/check_state_topology.py
python scripts/check_enterprise_ai_superiority.py --json
python scripts/check_enterprise_ai_implementation_notes.py --json
```

Local isolated-source overlay: **47 focused tests passed** before the
canonical repository test module was committed. Those tests are not a
substitute for GitHub exact-head checks. On this draft PR, Repository
Hygiene and Secret Scanning passed for the phase-four commit; Merge
Readiness, Backend Quality and App Foundation E2E were **skipped**.
Do not merge on that basis. Promote only after runtime authority,
schema/state topology updates, write/restore drills, operator controls,
privacy deletion, and fail-closed CI evidence are complete.

## Phase 5: authority-resolved guarded local inference facade (2026-10-27)

`skeleton/ai/runtime/inference/guarded_service.py` now implements
`CanonicalGuardedLocalService` above the existing
`GuardedLocalInference` and canonical `LocalInferenceEngine`.
It does not create a new inference provider or credential owner.

Before executing, the service resolves `TrustedContextSnapshot` from an
injected **trusted, tenant-authorized reader**, bound by context ID and
deterministic request digest. It checks tenant/context equality and rejects
caller attempts to override `snapshot`, `prepared_input`, delivery
contract or tenant authority. The existing wrapper then checks the pinned
Merkle root and instruction digest, native-renderer/tokenizer echo,
independent adversarial verdict and sampler/output contract.

After the model has generated but **before** returning any response, the
service re-reads the same authoritative snapshot. A changed version,
instruction policy, root, context or tenant binding raises
`SealedContextReplayError`, withholding the entire result. A
`GuardedGeneration` includes the pre-delivery receipt and the accepted
canonical snapshot version only after both checks succeed.

This is **not yet a mandatory global intercept**: the product's provider
composition root must route protected local generations through the new
service and block direct unguarded entrypoints, including native streaming
paths, cache hits, batching and tool calls. The snapshot-reader implementation
must come from existing canonical conversation authority, not the client.
Production additionally requires a real separate review model, a verified
tokenizer/sampler capability and explicit timeouts/quotas. Passing a test
mock reviewer or a permissive `sampler_support` callback does not prove
prompt-injection immunity or grammar-constrained decoding.

The dedicated `skeleton/testing/test_guarded_local_service.py` module
covers authorized stable generation, a concurrent canonical edit,
cross-tenant failure, and attempted prepared-tensor bypass.

### Current scope and acceptance

The focused isolated-source checks report **51 passing** across all seven
sealed context, archive, storage and guarded inference test files. The
documented example still needs exact-head GitHub tests under the full
repository environment, including all mandatory architecture validators.
The SQLite CAS is a reference-only persistence boundary; Mongo outbox,
majority durability, privacy erasure, key lifecycle, external monotonic
witness and production local-inference routing are not yet activated.

Cryptography cannot eliminate LLM attention fading, hallucinations, prompt
injection by itself, or finite context windows. Model-side internal thoughts
and proprietary provider KV tensors remain unavailable unless their runtimes
expose independently consented, version-compatible state export.


## Full-chain audit and verified retrieval integrity (2026-10-27)

`skeleton/context/sealed_memento_audit.py` exposes
`audit_memento_chain` for the SQLite conformance owner and
`audit_memento_chain_async` for the production-shaped Mongo reader.
Both obtain a catalog head **independently** before and after the scan,
read a maximum of 2,000 events per page, pin each page's starting head,
check every exact-next global sequence, reject thread version drift,
cross-check counts of user/LLM/delivered-work events, and produce a
domain-separated deterministic transcript digest without returning any
recovered plaintext in the audit receipt.

This is a bounded **verification operation**, not a lossless expansion
of the model context window or a claim that a syntactically well-formed
conversation was fully attended to by a model. Audit capacity is capped
at 512 pages (up to 1,024,000 events), must be operator-budgeted, and
fails closed when the scan cannot complete. Each page's owner-backed
reader remains responsible for AES-GCM replay and independently
persisted checkpoint verification. The digest must remain in authorized
operational evidence; it is not an external rollback-resistant signature.

`skeleton/context/sealed_memento_retrieval.py` additionally pins
all causal expansion windows to the previously authenticated head and
checks point-read checkpoint serials, page counts and terminal flags.
Fault-injection tests cover cross-page gaps, deleted/inconsistent
prefixes, replaced resume heads, lost point reads, versions changing
during retrieval, and truncation at the scan budget.

**Deployment gaps:** no independent monotonic off-database head witness
or KMS-backed disaster-recovery evidence yet; the optional guarded
local-inference facade still requires production composition routing,
native tokenizer/sampler attestation, and exact-head CI qualification.
A passing local focused test suite or a skipped CI job is not merge
readiness. Mongo transaction durability requires replica-set or sharded
transaction support; do not silently downgrade to standalone writes.

## Phase 13-14 delivery validation (2026-10-27)

The guarded local inference path now validates nested JSON with the strict and bounded delivery_schema module at admission and before release. Both the contract schema and native sampler schema are pinned across a generation call, and unexpected mutation rejects the result. Unsupported schema keywords, duplicate keys, nonfinite values, invalid Unicode, and excessive structure are rejected. This is not native sampler certification.

Regex delivery now uses delivery_regex with an explicitly declared timeout-capable regex dependency. Regex patterns are limited to 2048 bytes, result strings to 64 KiB, and individual matches to 50 ms. Missing matcher support, invalid patterns and timeouts reject delivery. These are post-generation checks, not proof of model understanding or provider enforcement.

The isolated focused regression suite passed 150 tests. Full exact-head Merge Readiness, Backend Quality and E2E qualification is still pending; skipped jobs cannot certify release.


## Phase 17 extensions: native tokenizer and streaming release safety (2026-10-27)

The canonical `ServerState` engine startup now accepts one application-owned
`ProtectedLocalComponents` binding before creating its provider registry.
The `CanonicalCompiledSnapshotReader` derives a Merkle root from the
currently authorized compiled request source, enforces an independently pinned
instruction digest, caps history/prompt allocations and refuses revoked,
version-changed or cross-tenant records. The source loader itself remains
an **unimplemented production dependency**: it must authenticate the source
against canonical execution and conversation records, and check revocation on
each read. No raw user/context digest is accepted as an authority witness.

`bind_native_transformer_guard` supplies encode/decode callbacks from the
actual `NativeLLMRuntime.tokenizer` and binds tokenizer digest, runtime
identity and callable ownership. The GGUF path remains fail-closed until an
equivalent native tokenizer proof exists; no byte-codec substitution is
considered native attestation. Prompt bytes that cannot round-trip through
the active native tokenizer cannot be admitted without explicit, audited
normalization and proof of equivalence.

Protected composition invokes tokenizer identity attestation before and after
model inference. A midflight swap or verifier outage rejects delivery.
Provider streaming remains a *buffered projection of the fully verified
result*, not a native token-by-token unreviewed stream. Regression tests
verify that a changed canonical version or forged output receipt emits zero
stream deltas. This does not establish native streaming safety; arbitrary
raw native token callbacks must not be exposed as a public route.

The protected guard is an in-process trusted-component boundary, not a secure
sandbox against arbitrary attacker-controlled Python executing inside the
same process. Final production qualification still requires a persistent
canonical loader with an independently administered monotonic witness, KMS
integration, an independently managed reviewer, security review and full
exact-head required checks. Skipped jobs remain *uncertified*.


## Phase 18: Native transformer tokenizer custody

`skeleton.ai.runtime.inference.build_guarded_native_transformer_adapter`
constructs a real native transformer backend *before* creating its protected
context guard. The bridge in `native_guard_binding.py` captures the exact
`NativeTokenizer.encode_ids` and `NativeTokenizer.decode_ids` bound methods
and pins the admitted model, runtime and tokenizer identity digests.
`verify_native_tokenizer` rejects a different backend, replacement callbacks,
backend identity drift and any tokenizer or native-runtime attestation failure.
The local inference guard repeats that identity check both before inference
and before returning output. These are backend-bound identity checks, not
cryptographic proof that the model understood the prompt.

**Strict fail-closed token fidelity:** The tokenizer must decode the *actual
rendered prompt* to the identical UTF-8 byte sequence. Native tokenizers with
unknown-token substitutions, normalization changes or otherwise lossy decoding
cannot serve that prompt in this protected mode. Do not replace the real
native tokenizer with a byte-level test tokenizer merely to make admission pass.

Protected native startup additionally requires a separately operated,
currently authorized compiled-context snapshot reader and independent
reviewer, provided by the application composition root. The
`CanonicalCompiledSnapshotReader` is a bounded verifier over a required
canonical loader; that loader and its durable revocation/version custody
are **not** supplied automatically by a native model artifact.
Text-only native backends make no JSON grammar, tool-execution or alternate
projection attestations.

The additive `Sealed Context Guard` workflow exercises the native adapter
factory, exact callback binding, tokenizer drift, negative startup cases and
pre/postflight output suppression. This workflow does not substitute for
full Merge Readiness, Backend Quality, App Foundation E2E, KMS and production
restore testing. Do not promote this draft to an end-to-end zero-loss claim.

## Phase 18: postflight native-input and sampler revalidation

The protected local path must reattest native prompt projection, sampler
grammar support and tokenizer identity after execution and before any response
byte is returned. The guard now records a domain-separated SHA-256
commitment over the exact admitted sequence of bounded unsigned 64-bit token
IDs, and computes that commitment again during postflight. A changed
token-to-ID mapping is detected even if the revised tokenizer decodes back
to identical UTF-8 prompt text. The protected provider refuses a receipt
missing this token sequence commitment; the buffered stream does not emit
deltas on missing evidence or canonical source/version drift.

These safeguards do not prove model comprehension, eliminate native
implementation defects, or replace independent authorization. The
domain-separated token commitment is a deterministic integrity receipt,
not a cryptographic signature from a separate protected hardware boundary.
Native tokenizer verification remains runtime-specific. Full product
qualification requires the canonical source reader to be populated from
authorized durable execution state and a production-native tokenizer binding,
as well as complete exact-head Merge Readiness, backend, installation and E2E.
Skipped jobs must not be represented as success.


## Phase 18: independently reloaded compiler source-custody inventory

`CanonicalSegmentSourceAuthority` (in
`skeleton/ai/runtime/inference/canonical_source_custody.py`) implements
the live `CurrentSourceAuthority` interface consumed by
`EngineSubmissionCompiledInputLoader`. The operator-owned
`CanonicalSourceCollectionLoader.read_current` must retrieve the **entire
current authorized compiler candidate set**, including candidates omitted
from the final prompt by policy or budgeting. The verifier recomputes a
deterministically sorted `(segment_id, content_digest)` inventory from
the materialized `ContextSegment` contents and their exact bytes. It
rejects foreign tenant scope, changed actor/context, deletion, revocation,
missing content, tampering, duplicate IDs and invalid source versions.
Admission caps are 2,000 candidates, 4 MiB per candidate and 16 MiB total.

This adapter never treats the compiled handoff itself as a current source
reader. An operator must connect its loader to each canonical source owner;
until then the app cannot claim globally operational guarded local inference.
The scoped durable bridge independently rechecks source custody and engine
execution state. Those reads are **not** a single cross-database
transaction; concurrent post-check revocation remains a deployment/locking
and finalization-design concern.

An additive GitHub Actions regression passed **310 tests** at the initial
Phase 18 head, covering the focused local provider, context, sealed archive,
Mongo and witnessed recovery suites. Additional durable-engine integration
tests explicitly bind the reconstructed candidate list to existing execution
ownership and reject mutation/revocation with unchanged prompt text.
Full Merge Readiness, Backend Quality, E2E and skipped release gates remain
mandatory before promoting the draft PR.


## Phase 19 — live canonical ownership and writer fencing (review-only)

The protected engine now has a real, task-scoped application composition path:

1. At trusted application initialization, provision and inject one
   `MongoCanonicalSourceEpoch` into the existing
   `MongoConversationAuthority` and `MongoMemoryRepository`. Their
   canonical mutation entrypoints advance the same majority-durable
   actor-scoped source epoch. The migration operator must initialize each
   tenant/actor record under a quiescent write freeze using
   `provision_migration_epoch`; reads and model requests never initialize
   authority implicitly.
2. Install attested `ProtectedLocalComponents` using
   `ServerState.configure_engine_local_guard` before engine startup.
   Separately call `ServerState.configure_engine_canonical_mongo_owners`
   with the **same** source epoch, canonical source owners and an
   independently pinned instruction-policy SHA-256.
3. `ServerState.bind_engine_execution_service` creates the *actual*
   `EngineExecutionService`, then builds
   `MongoExecutionConversationResolver` and
   `CanonicalExecutionSourceFactory` using that service. The native
   provider receives `ScopedEngineCompiledSnapshotReader` under the
   existing guarded local composition path.
4. Every protected request resolves its conversation through the actual
   Mongo conversation *user message* and digest-verified
   `_chat_engine_command`, comparing that immutable command to the
   separately persisted execution. The original thread authorization
   verifies tenant, actor, active branch and lifecycle. The
   `CanonicalOwnerSourceCollectionLoader` independently reconstructs
   the entire current active conversation and optionally canonical memory
   subject records. The existing engine bridge verifies both source
   custody and execution identity before native execution and after it.
5. A live conversation/memory mutation moves the actor's epoch to an odd
   `writing` state **before** canonical state changes, and advances it
   to the next even `stable` value only after the canonical mutation
   returns. Concurrent or missing writer state denies context reads.
   An exception, crash, incomplete majority write, uncertain write result
   or lost CAS leaves the epoch **quarantined**, requiring an independently
   audited repair procedure; never time-expire, steal or auto-reset it.

### Guarantee boundaries

- This is a writer-enforced seqlock and reread consistency boundary,
  **not** a cross-database atomic transaction, external consensus quorum
  or a proof that unrelated writers cannot change Mongo. Production
  activation requires every relevant writer, deletion and restore path
  to participate. An uninstrumented application route invalidates the
  stronger cross-owner guarantee.
- Source candidate families outside canonical conversation and governed
  memory (retrieval, tools, artifacts, skills, policies, derived Dragon
  context) are **not silently verified**. Their presence causes an
  inventory mismatch and protected inference fails closed until their
  canonical owners are integrated.
- Unrelated direct calls to the raw engine are still denied by guarded
  engine policy; the startup factory only activates protection when the
  deployment supplies real independent model/tokenizer attestations,
  sampler attestation and the reviewer.
- The `MongoExecutionConversationResolver` intentionally supports only
  the canonical direct `_chat_engine_command` path. Edited request
  `_chat_execution` and regeneration requests require separate
  fully owner-validated bindings before protected execution.
- The source epoch must be persisted with majority concern on the same
  trusted canonical Mongo cluster. Restore, failover and deletion need
  externally attested drills. It is not the separate monotonic KMS/head
  witness for the sealed memento archive.
- This remains a **draft / release-blocked** feature until full exact-head
  Merge Readiness, Backend Quality, App Foundation E2E, Artifact Policy,
  Malware Gate and Workflow Input Security succeed, alongside the
  unimplemented operator migration, crash recovery and model-specific
  attestation drills. Skipped jobs are not passes.

