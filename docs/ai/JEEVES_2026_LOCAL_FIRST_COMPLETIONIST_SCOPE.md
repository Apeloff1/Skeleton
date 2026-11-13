# Jeeves — 2026 Local-Only Primary AI Completionist Buildscope

> **Planning status, not implemented functionality.** PR #5282 / branch `fix/first-install-ai-chat-prototype-20261112`. Existing qualified implementation at `0365be1a0166985f551e7a4cb95ec39b7123296d` is the starting source snapshot. Every new code commit changes the exact-head qualification requirement. This document is an actionable engineering backlog and integration contract; no proposed feature is marked done solely because it appears here.

## Product definition, end state, hard boundaries

Jeeves is the singular **primary locally executing text AI** across desktop workbench, CLI, application backend and connected phone client. The owner-provided GGUF weights and a SHA-pinned llama.cpp runtime must actually generate output on hardware owned by the operator. **No OpenAI/Anthropic/hosted fallback** is allowed, even when remote credentials exist. Additional modalities (image, audio, video and Dragon crawler source) are optional **reviewed text-only advisory evidence** until independently qualified local decoders exist. No advisory source can act as a second primary model, system instruction, execution privilege or rights waiver.

The 2026 product target includes a reliable, fast, restart-safe local chat interface; model identity/manifest custody; full conversation integrity and cancellation; adaptive CPU/GPU/unified RAM/swap/disk admission; private-first onboarding; explicit constrained tools and coding/Game Builder extensions; measurable quality and performance; and independent security/installer/device proof. **The present PR is a substantial reviewable prototype, NOT this completed target.**

### Established implementation starting points

| Plane | Current implementation surfaces (existing) | Claims we explicitly do NOT make |
|---|---|---|
| Model and provider admission | `skeleton/ai/jeeves_local_policy.py`, `skeleton/provider_runtime.py`, `backend/routes/ai.py` | Remote SDK constructors universally absent across every app path unless tested |
| GGUF and native runtime | `scripts/build_jeeves_local_manifest.py`, `skeleton/ai/runtime/inference/llama_cpp.py`, `skeleton/app/local_ai.py` | Operator GGUF loaded and performant on every target device |
| Conversation/storage | `skeleton/ai/model_runtime/offline_chat.py`, `skeleton/app/offline_http.py`, `skeleton/app/offline_web.py` | Every backup/SQLite corruption scenario fully qualified |
| Product install | `scripts/install_ai_chat.py`, `frontend/src/features/Setup/AppSetupWorkspace.tsx`, `docker-compose.yml` | Physical Windows/mobile end-to-end release qualified |
| Advisory | `skeleton/app/jeeves_advisory.py`, `skeleton/app/offline_grounding.py` | Raw media decoded by a local multimodal model or independently verified |
| Live qualification | `scripts/qualify_jeeves_live_local.py`, `tests/test_jeeves_live_local_advanced.py`, source CI | Untrained TinyTransformer source fixture proves real GGUF language quality |

## Cross-PR dependency graph and ownership

`#5281 Dragon research/Atlas` → only reviewer-consented, rights-scoped passages may flow into `#5282 Jeeves advisory grounding`. `#5282` defines primary local model, chat/session, installer and protected app interfaces. `#5283`, stacked on #5282, extends OS process/SQLite inference custody and orphan-worker containment. Cross-link documents, but do not duplicate authority or merge order. The Builder/Shell/automation/game-production work remains future governed tools extending Jeeves, not an alternate primary model.

**Quality evidence order:** synthetic unit contract → genuine native tiny-model source test → actual operator GGUF process → authenticated multi-service product chat → clean installed binary → physical devices and pressure/recovery → independent release/security. No stage substitutes for the next.

## Definition of complete for a work package

A package is **PLANNED** unless code, ownership, architecture seam, versioned API/schema, bounded latency/storage/memory/resource allocation, a success test, a malicious/negative test, exact-head CI, instrumented recovery where relevant, documentation and compatibility review are all present. Model-specific, cross-device, license/security or release claims additionally require independent evidence. No package's mere presence in this ledger counts toward completion.

## Execution waves and dependency gates

1. **C0 / First Useful Chat:** finish J01–J03, J05–J06: real pinned GGUF → local execution → authenticated chat → durable receipt. No hosted mode, no fake completion.
2. **C1 / Durable Trust:** J04 and J12: all-history integrity, provenance, replay, cancellation and privacy guards must survive restart and tamper.
3. **C2 / Human-Governed Intelligence:** J07–J08 and J11: advisory context, permissions and typed tool plans without autonomous privileged writes.
4. **C3 / Hardware Frontier:** J09, J13: adaptive unified memory, safe local offload, pressure-aware concurrency, measured target-device performance.
5. **C4 / Consumer Product:** J10 and J14: usable UX, physical-device install, qualified rollback/support artifacts, release evidence.

## 168 individually testable build packages across 14 domains


### J01 — Local-first identity, registry and provider isolation

**Primary source seams:** `skeleton/ai/jeeves_local_policy.py; skeleton/provider_runtime.py; backend/routes/ai.py`. **Initial qualification file:** `tests/test_jeeves_local_policy.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-01-01: Make jeeves the singular primary model identity for new chats across backend, desktop, CLI and UI.** *Required failure/abuse evidence:* Unknown model ID and any hosted alias deny before provider construction. **Status: PLANNED; no release assertion.**
- **JV-01-02: Enforce JEEVES_LOCAL_ONLY and explicit local provider mode as mutually consistent typed config.** *Required failure/abuse evidence:* Conflicting env settings do not silently reinterpret the primary model. **Status: PLANNED; no release assertion.**
- **JV-01-03: Forbid fallback paths to OpenAI, Anthropic, XAI or any remote SDK even when credentials exist.** *Required failure/abuse evidence:* Secret canaries and mock SDK constructors prove zero remote initiation. **Status: PLANNED; no release assertion.**
- **JV-01-04: Fence model catalog and ready flags to the exact active local model, not any installed inventory.** *Required failure/abuse evidence:* Second model, disabled model or foreign alias never appears selectable. **Status: PLANNED; no release assertion.**
- **JV-01-05: Bind model, tokenizer, runtime, policy and generation settings to a versioned identity digest.** *Required failure/abuse evidence:* Identity mutation invalidates readiness and new generation without corrupting history. **Status: PLANNED; no release assertion.**
- **JV-01-06: Establish explicit no-model, model-not-pinned, missing-file and model-not-loaded states.** *Required failure/abuse evidence:* False healthy metadata does not masquerade as actual inference. **Status: PLANNED; no release assertion.**
- **JV-01-07: Deny untrusted local plugin or adapter override of the primary model resolution.** *Required failure/abuse evidence:* Plugin changes cannot silently replace Jeeves with another local or cloud model. **Status: PLANNED; no release assertion.**
- **JV-01-08: Make backend route validate local policy before touching conversation persistence.** *Required failure/abuse evidence:* Hosted request refuses without creating even an empty conversation row. **Status: PLANNED; no release assertion.**
- **JV-01-09: Require scope-bound auth at the engine service rather than relying on localhost alone.** *Required failure/abuse evidence:* Wrong bearer, swapped origin and cross-user calls never reveal state. **Status: PLANNED; no release assertion.**
- **JV-01-10: Make policy epoch observable without exposing secrets, file paths or protected provider config.** *Required failure/abuse evidence:* Error payload contains typed codes instead of internal stack traces. **Status: PLANNED; no release assertion.**
- **JV-01-11: Preserve historical read-only conversations after model drift, subject to integrity verification.** *Required failure/abuse evidence:* Model outage does not create a new reply or falsely attest a replay. **Status: PLANNED; no release assertion.**
- **JV-01-12: Define safe migration from hosted-first legacy config with explicit refusal and human operator action.** *Required failure/abuse evidence:* Legacy hosted tokens cannot be reused as local model authorization. **Status: PLANNED; no release assertion.**

### J02 — Genuine model installation, GGUF custody and trust chain

**Primary source seams:** `scripts/build_jeeves_local_manifest.py; scripts/install_ai_chat.py; skeleton/app/local_ai.py`. **Initial qualification file:** `tests/test_build_jeeves_local_manifest.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-02-01: Build canonical manifest from real operator-supplied weights and executable, never a synthetic placeholder.** *Required failure/abuse evidence:* Missing actual model bytes rejects with no green deployment claim. **Status: PLANNED; no release assertion.**
- **JV-02-02: Verify weights, tokenizer, binary, quantization metadata and runtime flags by SHA-bound admission.** *Required failure/abuse evidence:* Mutated weights or binary after manifest pin deny new work. **Status: PLANNED; no release assertion.**
- **JV-02-03: Establish bounded GGUF header/layout, tensor count, offset, vocabulary and length validation.** *Required failure/abuse evidence:* Malformed, cyclic or truncated GGUF does not reach executable launch. **Status: PLANNED; no release assertion.**
- **JV-02-04: Verify architecture support and context limits before application declares readiness.** *Required failure/abuse evidence:* Unsupported model family cannot be presented as working Jeeves. **Status: PLANNED; no release assertion.**
- **JV-02-05: Separate model download/import/license approval from local inference execution.** *Required failure/abuse evidence:* Offline operator cannot get a hidden remote model download. **Status: PLANNED; no release assertion.**
- **JV-02-06: Require private model storage, symlink protection and anti-TOCTOU rehash before spawn.** *Required failure/abuse evidence:* Replaced parent, hardlink alias and path traversal cannot swap admitted bytes. **Status: PLANNED; no release assertion.**
- **JV-02-07: Record reproducible runtime version, command profile, acceleration backend and digest.** *Required failure/abuse evidence:* Receipt identifies exact local executable and compatible runtime settings. **Status: PLANNED; no release assertion.**
- **JV-02-08: Handle model upgrade as a staged, reversible operator approval process.** *Required failure/abuse evidence:* Upgrade crash preserves old model and immutable conversation history. **Status: PLANNED; no release assertion.**
- **JV-02-09: Offer safe CPU-only mode when GPU unsupported, still running the same local model.** *Required failure/abuse evidence:* GPU failure never activates remote fallback or different model identity. **Status: PLANNED; no release assertion.**
- **JV-02-10: Support hardware-compatible quantization selection only from genuinely installed approved artifacts.** *Required failure/abuse evidence:* Requested low-memory mode cannot fabricate available quantization weights. **Status: PLANNED; no release assertion.**
- **JV-02-11: Make integrity check resumable for large files without trusting partial hashes.** *Required failure/abuse evidence:* Interrupted verification never marks the artifact qualified. **Status: PLANNED; no release assertion.**
- **JV-02-12: Define model-card and operating constraints with measured context, memory and license information.** *Required failure/abuse evidence:* Unverified speed, quality and ownership claims are labeled not measured. **Status: PLANNED; no release assertion.**

### J03 — Inference execution, prompting, tokenization and real output

**Primary source seams:** `skeleton/ai/runtime/inference/llama_cpp.py; skeleton/app/local_ai.py`. **Initial qualification file:** `tests/test_jeeves_live_local_advanced.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-03-01: Emit a real model-generated response for every successful chat result, no canned reply or fake readiness.** *Required failure/abuse evidence:* Success requires nonempty local output and execution receipt. **Status: PLANNED; no release assertion.**
- **JV-03-02: Render role-bound system/user/assistant messages using a pinned compatible chat template.** *Required failure/abuse evidence:* Delimiter injection cannot acquire system role or alter template semantics. **Status: PLANNED; no release assertion.**
- **JV-03-03: Preserve exact admitted tokenizer and token budget through prompt assembly and execution.** *Required failure/abuse evidence:* Whitespace, Unicode and special tokens cannot bypass context checks. **Status: PLANNED; no release assertion.**
- **JV-03-04: Reserve output/context tokens before invocation with fail-closed overflow handling.** *Required failure/abuse evidence:* Excessive prompt or negative budgets do not partially commit. **Status: PLANNED; no release assertion.**
- **JV-03-05: Enforce bounded runtime timeout, stdout/stderr capture and safe child termination.** *Required failure/abuse evidence:* Hung child and output flood cannot exhaust disk, RAM or worker slot. **Status: PLANNED; no release assertion.**
- **JV-03-06: Carry native execution receipt from model into durable SQLite with hash-chain checks.** *Required failure/abuse evidence:* Receipt and saved UTF-8 text cannot disagree after successful commit. **Status: PLANNED; no release assertion.**
- **JV-03-07: Expose actual output token count and latency separately from estimated progress.** *Required failure/abuse evidence:* No guessed tokens/sec presented as measured throughput. **Status: PLANNED; no release assertion.**
- **JV-03-08: Support cooperative cancellation with physical worker drain before releasing capacity.** *Required failure/abuse evidence:* Cancelled-but-running subprocess cannot overlap next request. **Status: PLANNED; no release assertion.**
- **JV-03-09: Preflight model identity again at actual subprocess spawn boundary, not only UI readiness.** *Required failure/abuse evidence:* Weight replacement after session creation fails closed. **Status: PLANNED; no release assertion.**
- **JV-03-10: Implement real in-process streaming only after stable chunk-sequence and final receipt protocol.** *Required failure/abuse evidence:* Interrupted stream never counts as committed answer. **Status: PLANNED; no release assertion.**
- **JV-03-11: Separate tool-use text generation from privileged tool execution and human approval.** *Required failure/abuse evidence:* Model-emitted JSON or commands cannot execute autonomously. **Status: PLANNED; no release assertion.**
- **JV-03-12: Guarantee first/second-turn context continuation via exact reopened history and tokenized preflight.** *Required failure/abuse evidence:* Second turn cannot silently discard first turn while claiming continuity. **Status: PLANNED; no release assertion.**

### J04 — Durable conversation, replay, backup and encryption

**Primary source seams:** `skeleton/ai/model_runtime/offline_chat.py; skeleton/app/offline_http.py`. **Initial qualification file:** `tests/test_jeeves_durable_integrity.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-04-01: Bind each turn to session id, request id, request SHA, model and tokenizer identity.** *Required failure/abuse evidence:* Changed request under same ID yields conflict with no new generation. **Status: PLANNED; no release assertion.**
- **JV-04-02: Use atomic CAS on conversation revision and append-only output receipt sidecars.** *Required failure/abuse evidence:* Concurrent writes cannot create two revisions at same index. **Status: PLANNED; no release assertion.**
- **JV-04-03: Verify every historical assistant text digest, not only the latest turn.** *Required failure/abuse evidence:* A forged early response denies continuation. **Status: PLANNED; no release assertion.**
- **JV-04-04: Verify execution receipt authenticity within supported local trust boundary.** *Required failure/abuse evidence:* Unknown or retroactively attached receipt cannot pose as genuine model run. **Status: PLANNED; no release assertion.**
- **JV-04-05: Expose read-only committed retry and restart recovery even if model unavailable.** *Required failure/abuse evidence:* Replay does not consume inference or modify response text. **Status: PLANNED; no release assertion.**
- **JV-04-06: Treat failed, cancelled and unknown tickets as explicit terminal/uncertain states.** *Required failure/abuse evidence:* Uncommitted output cannot appear successful. **Status: PLANNED; no release assertion.**
- **JV-04-07: Support signed/encrypted local backup with explicit key custody and schema versions.** *Required failure/abuse evidence:* Tampered, truncated or wrong-key archive cannot restore partial history. **Status: PLANNED; no release assertion.**
- **JV-04-08: Keep portable import/fork distinguishable from actual runtime execution evidence.** *Required failure/abuse evidence:* Imported turn does not acquire a fictional model execution receipt. **Status: PLANNED; no release assertion.**
- **JV-04-09: Handle filesystem crash, disk full and WAL corruption with explicit recovery plan.** *Required failure/abuse evidence:* No partial successful reply on commit failure. **Status: PLANNED; no release assertion.**
- **JV-04-10: Implement bounded retention, export and delete with privacy-safe tombstones.** *Required failure/abuse evidence:* Deleted conversation cannot be reconstructed through live search indexes. **Status: PLANNED; no release assertion.**
- **JV-04-11: Protect data migration compatibility and reversible rollback where format allows.** *Required failure/abuse evidence:* Older app never silently misparses new receipt schemas. **Status: PLANNED; no release assertion.**
- **JV-04-12: Bind advisory evidence and citations to conversation revision and source permissions.** *Required failure/abuse evidence:* Revoked evidence is not silently reintroduced on restore. **Status: PLANNED; no release assertion.**

### J05 — Authenticated HTTP, backend bridge and tenancy

**Primary source seams:** `skeleton/app/offline_http.py; backend/routes/ai.py; frontend/src/product/chatSessionClient.ts`. **Initial qualification file:** `backend/tests/test_ai_chat_local_engine_e2e.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-05-01: Keep offline model HTTP bound to loopback by default and refuse remote bind without explicit guarded design.** *Required failure/abuse evidence:* Foreign socket and Host header spoof cannot reach model. **Status: PLANNED; no release assertion.**
- **JV-05-02: Require constant-time bearer check with bounded parser and request-size limits.** *Required failure/abuse evidence:* Wrong/same-length token and malformed JSON return no private contents. **Status: PLANNED; no release assertion.**
- **JV-05-03: Implement explicit local session CRUD, async turn lifecycle, cancel and read-only recovery APIs.** *Required failure/abuse evidence:* Status cannot invent a result or skip stored receipt verification. **Status: PLANNED; no release assertion.**
- **JV-05-04: Enforce tenant-scoped backend conversation/session authority on every bridge hop.** *Required failure/abuse evidence:* User A cannot query, cancel or export user B's turn. **Status: PLANNED; no release assertion.**
- **JV-05-05: Ensure backend-to-engine capability credentials never enter client logs or mobile bundle.** *Required failure/abuse evidence:* Token canaries absent from JS bundle, analytics and error responses. **Status: PLANNED; no release assertion.**
- **JV-05-06: Provide typed client response/error unions for ready, busy, open-circuit, cancelled and failed.** *Required failure/abuse evidence:* Unsupported response shape fails closed, not interpreted as assistant text. **Status: PLANNED; no release assertion.**
- **JV-05-07: Handle HTTP 409 idempotency conflict and 423 busy separately with actionable UX.** *Required failure/abuse evidence:* Busy does not trigger automatic duplicate POST. **Status: PLANNED; no release assertion.**
- **JV-05-08: Support deadline/abort for requests with read-only reconciliation after uncertain transport.** *Required failure/abuse evidence:* Network timeout cannot silently submit again with changed request ID. **Status: PLANNED; no release assertion.**
- **JV-05-09: Pin service identity, deployment epoch and model digest in mobile/desktop handshakes.** *Required failure/abuse evidence:* Reconnecting to wrong host refuses rather than showing foreign history. **Status: PLANNED; no release assertion.**
- **JV-05-10: Block backend providers from fabricating model identity or local receipt data.** *Required failure/abuse evidence:* A remote model cannot self-report local:jeeves and bypass policy. **Status: PLANNED; no release assertion.**
- **JV-05-11: Harden error redaction against backend native path, shell output and secret exceptions.** *Required failure/abuse evidence:* Private model paths and tokens absent from public ticket JSON. **Status: PLANNED; no release assertion.**
- **JV-05-12: Provide revocation, token rotation and loopback listener restart procedures.** *Required failure/abuse evidence:* Expired credentials deny while canonical SQLite remains available. **Status: PLANNED; no release assertion.**

### J06 — First install, private packaging, desktop and mobile connectivity

**Primary source seams:** `scripts/install_ai_chat.py; frontend/src/features/Setup/AppSetupWorkspace.tsx; docker-compose.yml`. **Initial qualification file:** `tests/test_install_ai_chat.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-06-01: Build first-user guided install sequence from model discovery to verified chat.** *Required failure/abuse evidence:* No terminal knowledge assumed where supported installer UI exists. **Status: PLANNED; no release assertion.**
- **JV-06-02: Make installer distinguish source qualification, real GGUF execution and protected full-app readiness.** *Required failure/abuse evidence:* Source-only green never turns into release-ready badge. **Status: PLANNED; no release assertion.**
- **JV-06-03: Generate private env and read-only bind mounts without exposing secrets in process argv.** *Required failure/abuse evidence:* Temp files, logs and zip output do not leak keys. **Status: PLANNED; no release assertion.**
- **JV-06-04: Qualify Windows 11/WSL2, Linux, macOS Intel/Apple silicon independently.** *Required failure/abuse evidence:* A green Linux run cannot authorize Windows-native claims. **Status: PLANNED; no release assertion.**
- **JV-06-05: Support Android/iOS as authenticated clients of user's own local host with explicit LAN/TLS policy.** *Required failure/abuse evidence:* Client connectivity is not mislabeled as offline on-phone inference. **Status: PLANNED; no release assertion.**
- **JV-06-06: Provide well-defined disconnected-phone state with no hosted fallback.** *Required failure/abuse evidence:* No internet or local host shows unavailable, not fabricated answer. **Status: PLANNED; no release assertion.**
- **JV-06-07: Support model storage locations with long path, Unicode and permissions validation.** *Required failure/abuse evidence:* Installer does not delete user's model or private SQLite on failure. **Status: PLANNED; no release assertion.**
- **JV-06-08: Make install resumable and idempotent with source/provenance bound checkpoints.** *Required failure/abuse evidence:* Interrupted provision does not duplicate secrets or migrations. **Status: PLANNED; no release assertion.**
- **JV-06-09: Implement full uninstall/reinstall preserving user databases with explicit opt-in purge.** *Required failure/abuse evidence:* Uninstall never silently destroys private conversation. **Status: PLANNED; no release assertion.**
- **JV-06-10: Qualify Docker Compose with actual model bind, health, quota and network isolation.** *Required failure/abuse evidence:* Started containers without live GGUF reply do not pass. **Status: PLANNED; no release assertion.**
- **JV-06-11: Implement signed, reproducible installation artifacts with SBOM and rollback ledger.** *Required failure/abuse evidence:* Unverified bundle cannot be considered release-qualified. **Status: PLANNED; no release assertion.**
- **JV-06-12: Provide device-specific error and recovery scripts for first message and reconnect.** *Required failure/abuse evidence:* Model not loaded, memory pressure and stale auth have distinct remedies. **Status: PLANNED; no release assertion.**

### J07 — Advisory-only multimodal and reviewed evidence

**Primary source seams:** `skeleton/app/jeeves_advisory.py; skeleton/app/offline_grounding.py`. **Initial qualification file:** `tests/test_jeeves_advisory.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-07-01: Keep image/audio/video/crawler evidence a separate reviewed observation path.** *Required failure/abuse evidence:* Observation does not change Jeeves primary model. **Status: PLANNED; no release assertion.**
- **JV-07-02: Record source type, declared source digest and server-verified observation digest separately.** *Required failure/abuse evidence:* Caller-claimed media digest is never represented as independently verified. **Status: PLANNED; no release assertion.**
- **JV-07-03: Require explicit human review/consent before adding text observations to local knowledge.** *Required failure/abuse evidence:* Auto caption cannot become trusted evidence without approval. **Status: PLANNED; no release assertion.**
- **JV-07-04: Version advisory schemas with bounded title, source, observation and access scope.** *Required failure/abuse evidence:* Oversized or unknown modality fails instead of truncating silently. **Status: PLANNED; no release assertion.**
- **JV-07-05: Keep raw media decoding as optional separately qualified local-only adapter.** *Required failure/abuse evidence:* No cloud ASR/vision call hidden behind advisory mode. **Status: PLANNED; no release assertion.**
- **JV-07-06: Treat source text as untrusted and not executable prompt policy.** *Required failure/abuse evidence:* Advisory instructions cannot override system role. **Status: PLANNED; no release assertion.**
- **JV-07-07: Bind citation offset, text hash and rights version to any grounded answer.** *Required failure/abuse evidence:* Changed source invalidates citation display. **Status: PLANNED; no release assertion.**
- **JV-07-08: Separate relevance/search score from factual confidence and evidentiary authority.** *Required failure/abuse evidence:* High similarity cannot become trusted factual truth. **Status: PLANNED; no release assertion.**
- **JV-07-09: Allow explicit citation rejection and re-review when evidence expires.** *Required failure/abuse evidence:* Revocation removes future grounding but retains safe audit metadata. **Status: PLANNED; no release assertion.**
- **JV-07-10: Bound total retrieved pages, tokens, streams and compressed media memory.** *Required failure/abuse evidence:* Long video/document source cannot starve live chat. **Status: PLANNED; no release assertion.**
- **JV-07-11: Offer provenance preview showing exactly what model may see before grounded send.** *Required failure/abuse evidence:* User can cancel evidence inclusion without history mutation. **Status: PLANNED; no release assertion.**
- **JV-07-12: Prove advisory-disabled mode still provides genuine local text chat.** *Required failure/abuse evidence:* No advisory dependency required for first useful reply. **Status: PLANNED; no release assertion.**

### J08 — Jeeves tooling, programming assistant and human-authorized actions

**Primary source seams:** `skeleton/provider_runtime.py; frontend/src/features/Jeeves/GovernedChatWorkspace.tsx`. **Initial qualification file:** `tests/test_jeeves_local_policy.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-08-01: Define typed tool catalogs by capability, tenant, source and policy version.** *Required failure/abuse evidence:* Model text cannot directly grant a new tool. **Status: PLANNED; no release assertion.**
- **JV-08-02: Provide read-only inspect/search workflow before any filesystem modification.** *Required failure/abuse evidence:* Suggested code edits never auto-apply to protected repository. **Status: PLANNED; no release assertion.**
- **JV-08-03: Require explicit human approval for writes, PR creation, code execution and deploy.** *Required failure/abuse evidence:* No implicit approval from previous chat or model confidence. **Status: PLANNED; no release assertion.**
- **JV-08-04: Use diff-first, path-allowlisted and size-bounded patch application.** *Required failure/abuse evidence:* Symlink, traversal and binary overrun cannot escape workspace. **Status: PLANNED; no release assertion.**
- **JV-08-05: Add deterministic test-first verification plan per coding task.** *Required failure/abuse evidence:* Failed tests block completion claim and delivery. **Status: PLANNED; no release assertion.**
- **JV-08-06: Separate browser/network capability from local inference and user secrets.** *Required failure/abuse evidence:* Local chat is not a blanket web/connector permission. **Status: PLANNED; no release assertion.**
- **JV-08-07: Provide signed/capability-scoped work order with request id and expiry.** *Required failure/abuse evidence:* Stale task cannot execute after rights revocation. **Status: PLANNED; no release assertion.**
- **JV-08-08: Support dry-run tool simulation for destructive and broad operations.** *Required failure/abuse evidence:* No irreversible writes during dry run. **Status: PLANNED; no release assertion.**
- **JV-08-09: Track tool input/output hashes separately from model response receipts.** *Required failure/abuse evidence:* Unverified tool output cannot be promoted as factual truth. **Status: PLANNED; no release assertion.**
- **JV-08-10: Fence shell commands by environment, duration, network policy and artifact custody.** *Required failure/abuse evidence:* Model cannot request unrestricted shell as a side effect. **Status: PLANNED; no release assertion.**
- **JV-08-11: Expose cancellation and retry semantics for long build operations.** *Required failure/abuse evidence:* Restart cannot duplicate dangerous write actions. **Status: PLANNED; no release assertion.**
- **JV-08-12: Integrate independent adversarial reviewer without making it a second primary chat model.** *Required failure/abuse evidence:* Reviewer disagrees/blocks; primary generation remains one local Jeeves. **Status: PLANNED; no release assertion.**

### J09 — Adaptive hardware, GPU/CPU, RAM, VRAM and disk spill

**Primary source seams:** `skeleton/ai/runtime/inference/local.py; skeleton/ai/runtime/inference/llama_cpp.py`. **Initial qualification file:** `skeleton/testing/test_local_ai_gguf_qualification.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-09-01: Probe real CPU, GPU, system RAM, unified memory, VRAM and swap capacity per host.** *Required failure/abuse evidence:* Missing sensor is UNKNOWN, not infinite capacity. **Status: PLANNED; no release assertion.**
- **JV-09-02: Derive model-specific memory estimate for weights, KV, context, batch and runtime buffers.** *Required failure/abuse evidence:* Overlarge context request rejects before allocation. **Status: PLANNED; no release assertion.**
- **JV-09-03: Bound concurrent inference and preload admission based on live pressure samples.** *Required failure/abuse evidence:* Second stream cannot overcommit when first model consumes headroom. **Status: PLANNED; no release assertion.**
- **JV-09-04: Support CPU offload and GPU layer count only from validated runtime profile.** *Required failure/abuse evidence:* Runtime cannot silently alter model identity to meet speed target. **Status: PLANNED; no release assertion.**
- **JV-09-05: Treat on-board memory read-only or immutable when hardware requires coherency.** *Required failure/abuse evidence:* No unsupported direct GPU/board writes to private memory. **Status: PLANNED; no release assertion.**
- **JV-09-06: Implement bounded disk-backed context/temporary spill with explicit encryption and cleanup.** *Required failure/abuse evidence:* Disk full or corrupted spill never changes model response authority. **Status: PLANNED; no release assertion.**
- **JV-09-07: Protect temp prompt and stderr files from symlink replacement and external read.** *Required failure/abuse evidence:* Private content remains private across crash and retry. **Status: PLANNED; no release assertion.**
- **JV-09-08: Use monotonic budgets and pressure circuit to shed work before OOM.** *Required failure/abuse evidence:* Resource exhaustion returns typed overload, not a false answer. **Status: PLANNED; no release assertion.**
- **JV-09-09: Monitor thermal throttling and sustained power only when genuine sensor data exists.** *Required failure/abuse evidence:* Unknown thermal state not misreported as safe. **Status: PLANNED; no release assertion.**
- **JV-09-10: Support fair queueing across chat, tools and longform operations.** *Required failure/abuse evidence:* A crawler or document job cannot starve interactive chat. **Status: PLANNED; no release assertion.**
- **JV-09-11: Release GPU/CPU reservation only after native workers have physically drained.** *Required failure/abuse evidence:* Cancelled subprocess remains counted until OS exit. **Status: PLANNED; no release assertion.**
- **JV-09-12: Measure tokens/sec, p95 time-to-first-token, memory peak and end-to-end latency.** *Required failure/abuse evidence:* No synthetic benchmark substituted for operator GGUF device run. **Status: PLANNED; no release assertion.**

### J10 — User chat UX, accessibility and resilience

**Primary source seams:** `frontend/src/features/Jeeves/GovernedChatWorkspace.tsx; skeleton/app/offline_web.py`. **Initial qualification file:** `frontend/scripts/test-installed-chat-endpoint.cjs`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-10-01: Make first chat available immediately after verified local install with unambiguous input/send state.** *Required failure/abuse evidence:* Cannot send to hosted/foreign model even via stale UI. **Status: PLANNED; no release assertion.**
- **JV-10-02: Provide progressive model readiness: not installed, validating, loading, ready, busy, degraded.** *Required failure/abuse evidence:* Busy/unknown never appears as fully ready. **Status: PLANNED; no release assertion.**
- **JV-10-03: Show local model identity, exact execution source and privacy state in chat header.** *Required failure/abuse evidence:* Cloud provider never appears as hidden default. **Status: PLANNED; no release assertion.**
- **JV-10-04: Implement response state machine queued/running/cancelling/complete/failed/unknown.** *Required failure/abuse evidence:* Uncertain transport never displays partial as committed. **Status: PLANNED; no release assertion.**
- **JV-10-05: Offer explicit retry preserving original idempotency key after ambiguous transport.** *Required failure/abuse evidence:* Changed prompt under old key must refuse. **Status: PLANNED; no release assertion.**
- **JV-10-06: Preserve per-session draft text and selection without cross-account leakage.** *Required failure/abuse evidence:* Account switch destroys or isolates draft. **Status: PLANNED; no release assertion.**
- **JV-10-07: Add conversation search/history with immutable receipts and clear deletion flows.** *Required failure/abuse evidence:* Corrupt historical turn fails closed with explanation. **Status: PLANNED; no release assertion.**
- **JV-10-08: Render citations, code blocks and long outputs safely with copy/export controls.** *Required failure/abuse evidence:* Model text is not treated as executable HTML. **Status: PLANNED; no release assertion.**
- **JV-10-09: Provide accessible keyboard/touch controls, screen reader status and reduced motion.** *Required failure/abuse evidence:* Entire chat usable without mouse and without animation. **Status: PLANNED; no release assertion.**
- **JV-10-10: Support offline-to-LAN reconnection with explicit identity and session revalidation.** *Required failure/abuse evidence:* Host switch cannot silently load wrong session. **Status: PLANNED; no release assertion.**
- **JV-10-11: Expose cancellation latency and clear busy owner/pressure diagnostics without leaks.** *Required failure/abuse evidence:* No model path, tokens or prompts in public error text. **Status: PLANNED; no release assertion.**
- **JV-10-12: Implement safe streaming presentation and finalized receipt boundary when protocol qualifies.** *Required failure/abuse evidence:* Partial chunks never become durable/history success. **Status: PLANNED; no release assertion.**

### J11 — Operational Jeeves orchestration, supervision and Builder integration

**Primary source seams:** `skeleton/app/local_ai.py; skeleton/provider_runtime.py`. **Initial qualification file:** `tests/test_jeeves_local_policy.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-11-01: Define Jeeves as coordinating local assistant with explicit read-only planning vs authorized action.** *Required failure/abuse evidence:* Planning text cannot create implicit tool approval. **Status: PLANNED; no release assertion.**
- **JV-11-02: Separate supervisor, secretary, worker and traffic manager responsibilities into typed boundaries.** *Required failure/abuse evidence:* Workers cannot promote themselves to privileged supervisor. **Status: PLANNED; no release assertion.**
- **JV-11-03: Represent 1000 virtual workers as schedulable logical jobs, not 1000 uncontrolled processes.** *Required failure/abuse evidence:* Memory and fairness admission are measured, not guessed. **Status: PLANNED; no release assertion.**
- **JV-11-04: Use finite cohort and concurrency policies with starvation and pressure controls.** *Required failure/abuse evidence:* Burst requests cannot exhaust host or bypass queue. **Status: PLANNED; no release assertion.**
- **JV-11-05: Implement declarative task graph, leases, retries, handoff receipts and audit.** *Required failure/abuse evidence:* Task replay cannot duplicate writes or approvals. **Status: PLANNED; no release assertion.**
- **JV-11-06: Make code building and game-building capabilities extension modules, not model substitutions.** *Required failure/abuse evidence:* One local language model remains primary. **Status: PLANNED; no release assertion.**
- **JV-11-07: Expose governed shell operations with workspace-granted paths and review checkpoints.** *Required failure/abuse evidence:* User chat cannot silently read or write arbitrary files. **Status: PLANNED; no release assertion.**
- **JV-11-08: Integrate source-bound GitHub pull request workflows with exact-head review evidence.** *Required failure/abuse evidence:* Green ancestor run cannot authorize merging current branch. **Status: PLANNED; no release assertion.**
- **JV-11-09: Bound crawler-assisted coding research as externally sourced untrusted evidence.** *Required failure/abuse evidence:* Web page cannot set internal tool policy. **Status: PLANNED; no release assertion.**
- **JV-11-10: Support resilient stop/resume of long workflows and phase checkpointers.** *Required failure/abuse evidence:* After restart, pending action is visible but not duplicated. **Status: PLANNED; no release assertion.**
- **JV-11-11: Define a testable app-builder content contract for chapters, acts, scenes and worlds separately.** *Required failure/abuse evidence:* A proposed 100/1000/9999 world target is not a chat-release claim. **Status: PLANNED; no release assertion.**
- **JV-11-12: Provide typed downstream tool interfaces for Jeeves/Dragon/Builder/Shell policy plane.** *Required failure/abuse evidence:* Cross-plane operation cannot bypass tenant or release approval. **Status: PLANNED; no release assertion.**

### J12 — Security, privacy, isolation and adversarial robustness

**Primary source seams:** `backend/routes/ai.py; skeleton/app/offline_http.py; skeleton/app/jeeves_advisory.py`. **Initial qualification file:** `backend/tests/test_ai_chat_local_engine_e2e.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-12-01: Threat-model prompt injection through tools, documents, model template and multimodal advisory.** *Required failure/abuse evidence:* Untrusted text cannot become system/developer instruction. **Status: PLANNED; no release assertion.**
- **JV-12-02: Enforce least-privilege filesystem/device/network policy for model subprocess.** *Required failure/abuse evidence:* Native child cannot access unrelated credentials or outside workspace. **Status: PLANNED; no release assertion.**
- **JV-12-03: Harden CSRF/Host/origin/TLS policy for LAN client and loopback entrypoints.** *Required failure/abuse evidence:* Browser origin spoof cannot expose conversation history. **Status: PLANNED; no release assertion.**
- **JV-12-04: Bound all JSON and file input including Unicode, float, NaN, depth and duplicate keys.** *Required failure/abuse evidence:* Malformed body fails before allocation or persistence. **Status: PLANNED; no release assertion.**
- **JV-12-05: Protect model weight and executable path against symlink/hardlink/TOCTOU swaps.** *Required failure/abuse evidence:* Path replacement between verify and spawn is detected. **Status: PLANNED; no release assertion.**
- **JV-12-06: Use constant-time auth and rotation with no secret exposure in logs or receipts.** *Required failure/abuse evidence:* Wrong-token oracle does not disclose length or timing-sensitive internals. **Status: PLANNED; no release assertion.**
- **JV-12-07: Verify historical output SHA and local execution sidecar independently of UI cache.** *Required failure/abuse evidence:* Tamper evidence fails closed. **Status: PLANNED; no release assertion.**
- **JV-12-08: Do not trust model-reported tool outputs or citations without source verification.** *Required failure/abuse evidence:* Citations can't be self-attested by model text. **Status: PLANNED; no release assertion.**
- **JV-12-09: Test prompt, tool and error canary redaction through backend, engine and frontend.** *Required failure/abuse evidence:* No sensitive markers in network trace or collected artifacts. **Status: PLANNED; no release assertion.**
- **JV-12-10: Enforce rate, memory, CPU and queue denial without unsafe fallback.** *Required failure/abuse evidence:* Pressure doesn't enable hosted or privileged bypass. **Status: PLANNED; no release assertion.**
- **JV-12-11: Formalize no-telemetry-by-default for private chat content and per-user retention.** *Required failure/abuse evidence:* Monitoring records only nonsecret aggregate metrics. **Status: PLANNED; no release assertion.**
- **JV-12-12: Require security signoff on installer, dependencies, model license and runtime SBoM.** *Required failure/abuse evidence:* Unresolved critical issues block release. **Status: PLANNED; no release assertion.**

### J13 — Performance engineering, SLOs and quality evaluation

**Primary source seams:** `skeleton/ai/runtime/inference/local.py; scripts/qualify_jeeves_live_local.py`. **Initial qualification file:** `tests/test_jeeves_live_local_advanced.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-13-01: Define separate source, native fixture, operator GGUF and product-stack evidence tiers.** *Required failure/abuse evidence:* One tier cannot be substituted for another. **Status: PLANNED; no release assertion.**
- **JV-13-02: Measure p50/p95/p99 first-token, full-turn and restart latency on actual host.** *Required failure/abuse evidence:* Benchmark includes cold and warm model states. **Status: PLANNED; no release assertion.**
- **JV-13-03: Measure sustained tokens/sec, VRAM/RAM peak, thermal/power and disk spill behavior.** *Required failure/abuse evidence:* Device sensors and sampling window disclosed. **Status: PLANNED; no release assertion.**
- **JV-13-04: Evaluate context retention at short, long and maximum admitted budgets.** *Required failure/abuse evidence:* Trimmed prior turn is visible/denied rather than silently lost. **Status: PLANNED; no release assertion.**
- **JV-13-05: Run language quality suites with task accuracy, code tests, reasoning and hallucination metrics.** *Required failure/abuse evidence:* Untrained tiny model does not qualify quality. **Status: PLANNED; no release assertion.**
- **JV-13-06: Audit multilingual tokenizer integrity and Norwegian/English Unicode behavior.** *Required failure/abuse evidence:* CJK/emoji/composed input cannot mutate receipt digest. **Status: PLANNED; no release assertion.**
- **JV-13-07: Measure cancellation stop time and memory release under stress.** *Required failure/abuse evidence:* No overlapping GPU work after cancellation. **Status: PLANNED; no release assertion.**
- **JV-13-08: Test repeated crash/restart cycles and model/manifest mutation mid-run.** *Required failure/abuse evidence:* No partial commit, orphaned temp file or duplicate reply. **Status: PLANNED; no release assertion.**
- **JV-13-09: Profile fairness when chat, longform and crawler tools compete.** *Required failure/abuse evidence:* Interactive queue SLO and worker budget remain bounded. **Status: PLANNED; no release assertion.**
- **JV-13-10: Conduct load tests for 1/10/100 local client tabs without hidden remote usage.** *Required failure/abuse evidence:* Live model service enforces admission and latency budget. **Status: PLANNED; no release assertion.**
- **JV-13-11: Track quality regressions with frozen dataset, seeds, prompt template and version.** *Required failure/abuse evidence:* Model upgrade cannot silently degrade safety or fidelity. **Status: PLANNED; no release assertion.**
- **JV-13-12: Publish device-specific qualification report containing raw measurements and caveats.** *Required failure/abuse evidence:* No marketing readiness claim without reproducible evidence. **Status: PLANNED; no release assertion.**

### J14 — Release, support, qualification and lifecycle

**Primary source seams:** `docs/ai/INSTALLED_AI_CHAT_PROTOTYPE.md; .github/workflows/installed-ai-chat-prototype.yml`. **Initial qualification file:** `tests/test_ai_chat_installed_smoke.py`. For each work item the negative assertion is as important as the happy path; record exact running SHA.

- **JV-14-01: Require all named final-head CI gates to succeed, not skipped, cancelled or ancestor.** *Required failure/abuse evidence:* A queued job counts as unverified, never pass. **Status: PLANNED; no release assertion.**
- **JV-14-02: Run clean first-install smoke from actual binary and actual operator GGUF.** *Required failure/abuse evidence:* Compose/config existence not equivalent to a working model. **Status: PLANNED; no release assertion.**
- **JV-14-03: Run authenticated backend-to-engine-to-frontend real chat and durable read-only replay.** *Required failure/abuse evidence:* One apparent mock reply does not qualify product. **Status: PLANNED; no release assertion.**
- **JV-14-04: Qualify Windows 11/WSL2, Docker, Linux and macOS Apple silicon separately.** *Required failure/abuse evidence:* Apple M1 skipped and Windows untested remain hard holds. **Status: PLANNED; no release assertion.**
- **JV-14-05: Exercise real Android/iOS client against private local host and lost connectivity.** *Required failure/abuse evidence:* Phone client success does not claim on-device weights. **Status: PLANNED; no release assertion.**
- **JV-14-06: Run security, CodeQL, secret, malware, dependency, artifact, repository hygiene and workflow-input gates.** *Required failure/abuse evidence:* No bypass through changed labels or merge strategy. **Status: PLANNED; no release assertion.**
- **JV-14-07: Test backup/restore, installer rollback, model downgrade and private key recovery.** *Required failure/abuse evidence:* User history stays intact after failed migration. **Status: PLANNED; no release assertion.**
- **JV-14-08: Provide release provenance, signed artifacts and SBOM with exact model/runtime pin.** *Required failure/abuse evidence:* Unpinned executable cannot be shipped as qualified. **Status: PLANNED; no release assertion.**
- **JV-14-09: Validate source license, model rights and user-consent language.** *Required failure/abuse evidence:* Operator-owned model files don't imply publication rights. **Status: PLANNED; no release assertion.**
- **JV-14-10: Define staged rollout, feature flags, cohort kill switch and support diagnostic bundle.** *Required failure/abuse evidence:* Disabled flag doesn't delete user's SQLite data. **Status: PLANNED; no release assertion.**
- **JV-14-11: Prepare privacy statement, telemetry controls, accessibility and onboarding documentation.** *Required failure/abuse evidence:* App claims match what binary actually does. **Status: PLANNED; no release assertion.**
- **JV-14-12: Produce independent GO/NO-GO evidence ledger with named reviewer and open blockers.** *Required failure/abuse evidence:* Ready-for-review alone never authorizes merge, release or first-install claim. **Status: PLANNED; no release assertion.**

## Proposed versioned technical contracts (not yet exposed APIs)

| Proposed contract | Owner and bounded fields | Failure semantics |
|---|---|---|
| `JeevesDeploymentAttestation.v2` | local model ID; binary/weight/tokenizer/config SHA; source license; host/runtime profile; operator approval epoch | Any digest/source mismatch prevents **new** model execution; old verified history remains readable |
| `LocalGenerationOrder.v2` | tenant/session ID; request ID; SHA of role history, prompt, model, template and generation budget; deadline; cancel token; allowed tool manifest | Reused key with changed bytes => deterministic conflict, no generation |
| `LocalTurnReceipt.v2` | exact assistant-text SHA-256; model/runtime digest; token counts; source identity; SQLite revision; execution receipt and evidence pointer | Partial stream, interrupted worker or missing sidecar never counts as success |
| `JeevesConversationSnapshot.v2` | full history/revisions, hash-linked turns, immutable import/fork provenance, retention, encryption version | Historical corruption or unsupported migration blocks continuation |
| `JeevesAdvisoryEvidence.v2` | modality, reviewed observation hash, source claim hash, source-rights/tenant scope, TTL, evidence offsets | Non-reviewed raw media and expired rights cannot become grounded context |
| `JeevesToolPlan.v2` | model suggestion, approved action schema, human approval token, cwd/path allowlist, timeout, network policy, invocation digest | Model-generated text alone is never an executable permission |
| `JeevesResourceAdmission.v2` | observed memory/VRAM/unified RAM/swap, effective KV/context estimate, hardware source and timestamp, reserved bytes | Unknown sensors or excessive pressure fail closed; no fabricated safe-capacity claim |
| `JeevesDeviceEvidence.v2` | exact source SHA, OS/CPU/GPU/runtime, install artifact/model digest, cold/warm metrics, chat/recovery/security tests | Missing physical hardware or measured data => unqualified, not passed |

**Version warning:** `v2` rows are proposed successor schemas. No consumer may send or rely on them until migration adapters, canonical field validation, explicit capability negotiation and negative tests exist. Maintain backward compatibility with already persisted data and never silently reinterpret an old receipt.

## Failure injection campaigns required before product signoff

1. **Model drift:** mutate manifest, GGUF bytes, tokenizer, executable, owned path, prompt template, reserved output context and engine config during idle and during an active turn. No new work after mismatch; historical receipt remains honest.
2. **Concurrency and cancellation:** two local HTTP listeners, two OS processes, concurrent tabs and client disconnect. Only correctly admitted work executes and no unknown reply is treated as committed. #5283 owns cross-process lease.
3. **Storage safety:** corrupt early SQLite assistant row, execution sidecar, WAL, imported backup, staged portable envelope and foreign-model ID. No repaired-by-guess output or fraudulent native proof.
4. **Privacy and abuse:** bearer tampering, Host-origin attacks, prompt injection from crawled sources, timeout stderr, path traversal, symlink swap and remote SDK secret canary. No unapproved network or raw exception export.
5. **Pressure and device:** GPU OOM and throttling, low RAM/unified memory, swap thrash, disk full, tiny context, long prompt, overlong stdout, native child hang and forced process kill. All conditions return explicit bounded statuses.
6. **First-use and operator:** Windows 11/WSL2 Docker, Linux and macOS native, clean uninstall/reinstall with preserved data, Android/iOS LAN reconnect, offline phone truthfulness, version rollback.
7. **Truth:** source TinyTransformer is untrained and cannot represent a production language-quality benchmark; a green readiness GET does not prove actual generation.

## Public reliability and privacy SLO proposal (targets, not measurements)

- **Correctness:** zero accepted hosted-model fallback requests; zero foreign model identity accepted as Jeeves; zero duplicate committed request ID under CAS.
- **Availability:** all existing verified conversation reads remain available through local model outage **when storage is healthy**; otherwise clear failure without auto-generation.
- **Worker ownership:** every admitted turn eventually reaches completed, cancelled, failed or explicitly unresolved state; resource slots are not recycled before native child drain.
- **Latency:** establish measured host-specific p50/p95/p99 including model load, time-to-first-token, total turn, cancellation and restart; assign numerical targets only after benchmark baseline.
- **Privacy:** private chat content, raw credentials and filesystem paths excluded from default telemetry; opt-in diagnostic artifacts bounded, redacted and locally stored.
- **Performance:** CPU/GPU/Metal/CUDA/Vulkan offload claims tied to actual supported backend and measured resource guard; unsupported accelerators remain unqualified.

## Exact-head acceptance gate checklist

| Gate | Evidence that must be collected | Does source-only success qualify it? |
|---|---|---|
| Jeeves local-only policy / source suite | Source tests, native tiny-model and SQLite, true model identity | **Only that source tier** |
| Real GGUF execution | Operator manifest, matching SHA, two actual turns, server restart, receipts | **No** |
| Protected backend-to-engine chat | Authenticated real path, local-only receipt and canonical writer | **No** |
| First install / Windows & Docker | Clean machine, signed artifacts, actual model loading, post-install reply | **No** |
| Android/iOS connectivity | Authenticated local-host connectivity, revoke/reconnect, network loss | **No** |
| On-device phone weights | Actual phone-local model, RAM/thermal/storage measurements | **No; separate future port** |
| Security | CodeQL, malware, secret, workflow-input, dependency, artifact, repo hygiene, privacy | **No; all independent** |
| Release governance | Merge readiness, rulesets, real approvals, SBOM, license, rollback, operator signoff | **No** |

**Review rule:** GitHub Ready for Review is visibility only; no merge/auto-merge/release until all mandatory non-compensable checks are independently successful at the exact head. Pending, skipped, cancelled, ancestor or mocked checks are unqualified.

## 12-role work allocation and bounded parallelism

Proposed agent/reviewer lanes: model security, GGUF/native execution, tokenizer/chat, SQLite/backup, backend identity, mobile/desktop installer, advisory/Dragon, governed tools, resource fabric, accessibility, adversarial security, independent release. These are **planning roles**, not autonomously running workers or authority to change protected refs. Local orchestration may later schedule up to 1000 logical tasks in bounded cohorts, but must prove physical admission, fairness and policy before increasing concurrency. Each handoff should carry issue ID, exact SHA, allowed paths, positive and hostile fixtures, resource cap, security impact, clear stop condition and proof location.

## Cross-platform release/rollback and no-go

A new GGUF model cannot silently replace an existing user deployment; migrations and backups are create-only until verified, old model/runtime stays available for explicit rollback, secret rotation is distinct from model rotation, and private user data is never automatically uploaded. Treat unverified Windows Job Object cleanup, Docker first-install, Apple GPU pressure, operator GGUF quality, offline-phone model execution and protected backend governance as **hard separate holds**, not boilerplate to ignore. Under no circumstances does a 2026 ambitious target justify remote inference fallback or bypassing the agreed local-only architecture.
