# Jeeves — local-only model, real offline inference, advisory multimodal

**Jeeves is the ONLY primary chat model.** OpenAI and other hosted providers
cannot answer as Jeeves or become fallback models. The application uses one
genuine, operator-owned, digest-pinned local GGUF model with the *deployment
identity* **jeeves**. This identity does not imply the underlying weights
were trained from scratch by Skeleton. Retain their real source and license.

Multimodal capabilities (images, audio, video, crawler knowledge) are
**advisory evidence**. They cannot replace the primary local text generator,
authorize tools, turn into system instructions, or trigger a hosted-model
failover. The actual model and executable, not a mock or a header alone,
must generate a verified answer before inference can be called working.

## Desktop-first: use the existing offline Jeeves workbench

On an installed desktop with an already-approved GGUF, you can use the
native Jeeves workbench immediately, without Docker or a remote LLM provider:

    python scripts/launch_jeeves_desktop.py

Select the actual model and a private local state directory through the
window. This launches the existing real llama.cpp + private SQLite
ExecutionSpine desktop, with local memory/pressure controls. The model
must genuinely be installed; no answer is fabricated when it is missing.
This is an independent desktop local chat mode: it is **not a substitute**
for the protected backend guard required by the connected mobile/web
application.

## 1. Prepare a genuine local model

Acquire a licensed GGUF and a compatible llama.cpp CLI executable and verify
their source. Neither a licensed user model nor hardware is bundled with
this change. The optional provisioner can obtain publicly pinned Qwen
weights only with an explicit --download option:

    python scripts/provision_local_ai.py --help

Use approved files already on disk to stay fully offline. Create an immutable
Jeeves deployment manifest in a directory that already exists:

    python scripts/build_jeeves_local_manifest.py \
      --model /absolute/path/to/owned-model.gguf \
      --executable /absolute/path/to/llama-cli \
      --output /absolute/path/to/jeeves.json \
      --profile qwen3-completion-chat --context 4096 --threads 2

Choose a prompt profile compatible with the actual model; raw and
llama-completion-chat are alternatives. The builder reads and hashes the
GGUF and native executable, validates the model header and runtime pins,
and creates the manifest only if absent. No external provider is contacted.

## 2. Prove real local generation

On a host that can execute the pinned native runtime:

    python scripts/install_ai_chat.py \
      --deployment /absolute/path/to/jeeves.json \
      --live-local

This invokes the actual bounded offline llama.cpp process, validates a
nonempty completion, exact model and runtime identities, and outputs a
local execution receipt digest. It never prints the answer or a key.

**This proves host-side local inference, not yet the protected application
backend or a phone.** The exact executable must be compatible with the
host; Linux container builds may not execute directly on macOS/Windows.
There is no automatic fallback to OpenAI.

## Advanced live local qualification: two turns, restart, hardware measurements

The single-process model test above is a prerequisite, not the complete
local runtime acceptance. To exercise a real `jeeves` GGUF from end to end
through an **authenticated loopback HTTP server** and **real SQLite**:

    python scripts/qualify_jeeves_live_local.py \
      --manifest /absolute/path/to/jeeves.json \
      --timeout 180 --output-tokens 16

This performs two genuine local model generations with a complete server and
SQLite reopen between them. It verifies the original response by an
independent GET-only recovery, verifies the continued conversation, checks
identity-bound output digests, and reports measured output token throughput.
No fake model, remote provider, streaming estimate, or network host beyond
127.0.0.1 is used for model inference. The qualification additionally
sends a **negative authentication probe** (missing authority must fail with
HTTP 401) and a **committed request-ID rewrite probe** (changing the prompt
under a used ID must fail with HTTP 409). After both denials, the originally
committed conversation must remain unchanged in SQLite. Results include
`unauthenticated_local_query_denied` and
`committed_request_rewrite_denied`. These are actual service checks, not
claims of independently attested runtime security.

Model quality and protected production bootstrap are **not** certified by
this test. Completion is bounded and never reported successful when either
turn fails.

In the standalone local async API, an abnormal native worker exit must reach
a terminal failed ticket, release the single-device generation slot and
permit a new genuine local attempt. Failed tickets expose only stable public
failure categories; internal model paths, runtime stderr and other exception
details must not cross the HTTP boundary.

The first-install script can run the same advanced test before configuring
or starting the app:

    python scripts/install_ai_chat.py \
      --deployment /absolute/path/to/jeeves.json --live-local-suite

For an operator applying the private configuration in the same run, add
`--apply`; for service startup add `--start`. The advanced test separately
reports `application_chat_verified=false` until the protected backend's
authenticated product chat acceptance passes.

## Advisory-only multimodal sources: no second language model

The **localhost offline Jeeves service** exposes authenticated
`GET /v1/advisory/status` and `POST /v1/advisory/ingest` to import only
an explicitly reviewed local **textual observation** derived from images,
audio, video, crawler results or documents. These APIs do not decode media,
call external providers, run inference or change Jeeves's primary model.

An advisory request is a JSON object with `schema_version` set to
`skeleton.jeeves.advisory.v1`, `modality` set to one of
`image-caption`, `audio-transcript`, `video-frames`,
`crawler-excerpt`, `text-reference`; a bounded `title`, the
`observation` text (up to 12 KiB), its exact `observation_sha256`,
a `source_sha256`, and `reviewed: true`.

The server verifies the **observation** hash; the original media artifact
digest is explicitly treated as a **caller-declared claim** because the raw
media was not ingested or independently hashed by this endpoint. Approved
advisories are stored in the model-scoped offline knowledge authority with
source/chunk checksums and deduplication. Nothing is automatically injected
into a conversation. The user must make a separate `grounded: true` chat
request; the model sees any matched passages as untrusted user-context
references, not privileged instructions or a second answer source.

These endpoints belong to the separate localhost offline UI and are not
automatically reachable through the protected mobile/backend API. That
cross-plane integration and real device media decoding remain independent
qualification requirements.

## 3. Configure and start Jeeves's private application stack

Create the private env and Compose model binding:

    python scripts/install_ai_chat.py \
      --deployment /absolute/path/to/jeeves.json --apply

If replacing an existing environment, explicitly add --force to preserve
the existing valid persistent database and signing identities. Optionally
supply --admin-email and --admin-password-file to bootstrap an approved
administrator with a private password file.

Start the installed stack:

    python scripts/install_ai_chat.py \
      --deployment /absolute/path/to/jeeves.json \
      --apply --force --start

This selects AI_PROVIDER=local, JEEVES_LOCAL_ONLY=1,
JEEVES_PRIMARY_MODEL_ID=jeeves, AI_LOCAL_GUARD_REQUIRED=1, and pins one
read-only local deployment. The primary engine receives no hosted provider
key, verifier or secondary model. Docker builds may need internet access
for image/dependency acquisition, but model *inference* remains local.

A successful Compose start is only service orchestration. It does not
prove a model answer or grant authority to disable the local guard.

### Trusted protected-local admission is mandatory

A generic Compose stack cannot invent the genuine model tokenizer/sampler
attestations, independent adversarial reviewer, task-scoped canonical
snapshot reader, majority-durable Mongo writer epoch or reviewed native
bootstrap. The application composition root must bind these before the
engine is ready. Without them, report local_guard_unavailable. Never set
AI_LOCAL_GUARD_REQUIRED=0 or use the unsafe development acknowledgement
to claim a production model works. Local CLI generation is not a substitute
for the guarded product chat route.

## 4. Prove an authenticated Jeeves chat turn

Read-only account/engine/storage/model readiness:

    python scripts/ai_chat_installed_smoke.py \
      --base-url https://YOUR_BACKEND_HOST \
      --login-email owner@example.com

One real inference and durable canonical replay:

    python scripts/ai_chat_installed_smoke.py \
      --base-url https://YOUR_BACKEND_HOST \
      --login-email owner@example.com \
      --exercise --timeout 180

The exact model must have provider_id=local and model_id=jeeves. The request
explicitly pins both, even if automatic routing is nominally available.
Provider receipts must start with provider:local:. Hosted/advisory receipts,
incomplete model outputs, lost canonical assistant rows and replays that
change the answer all fail acceptance. No second POST occurs after an
uncertain network outcome.

Recover the original nonsecret IDs with GET-only requests:

    python scripts/ai_chat_installed_smoke.py \
      --base-url https://YOUR_BACKEND_HOST \
      --login-email owner@example.com \
      --recover-thread THREAD_ID --recover-request REQUEST_ID

For headless environments use --token-file with a private mode-0600 file,
never a password in command arguments. Interactive passwords require a
real terminal and are never echoed.

## 5. Android/iOS connectivity is not on-device inference

The mobile app connects to **your own authenticated backend**, not an
external AI API. To build an installed client:

    cd frontend
    EXPO_PUBLIC_BACKEND_URL=https://YOUR_BACKEND_HOST \
      npx eas build --profile apk --platform android

The local GGUF runs on the operator-owned computer/server. **The phone
is a client of that local host; it is NOT yet an independent on-device
offline model.** A disconnected phone would require a distinct native
Android/iOS inference module and real device memory/thermal qualification.
Do not equate a connected phone with locally resident phone weights.

## 6. Tests and release blockers

Focused source tests and native inference acceptance:

    python -m pytest -q --noconftest \
      tests/test_jeeves_local_policy.py \
      tests/test_jeeves_live_local_advanced.py \
      tests/test_jeeves_inference_circuit.py \
      tests/test_jeeves_durable_integrity.py \
      tests/test_jeeves_advisory.py \
      tests/test_install_ai_chat.py \
      tests/test_ai_chat_installed_smoke.py \
      tests/test_configure_ai_chat_hosted.py
    python -m pytest -q tests/test_app_offline_chat_cli.py
    cd frontend && node --test scripts/test-installed-chat-endpoint.cjs
    cd frontend && yarn typecheck

Real production deployment still needs an operator-owned model, actual
GGUF completion, protected engine bootstrap, canonical live chat test on
the installed app, restart recovery, hardware pressure checks, secure TLS
ingress and exact-head security/installer qualifications. This PR stays
review-only until these are proven.

| Failure | Safe response |
| --- | --- |
| No local model | Pin real licensed GGUF + llama.cpp as model_id=jeeves |
| Wrong provider or extra model | Reject; remove hosted and alternate inference routes |
| local_guard_unavailable | Install trusted snapshot/reviewer/tokenizer authorities |
| GGUF/runtime hash mismatch | Restore exact approved files and requalify |
| No local provider receipt | Reject as unverified, never substitute hosted output |
| Phone cannot reach backend | Configure own TLS ingress; never expose Mongo/engine |


## 7. November 2026 fail-closed inference reliability

Jeeves uses a process-local runtime failure circuit on the standalone
authenticated loopback service. The circuit is **not an alternate model**,
a cloud failover, a health-check completion, or a durable source of truth.

- Three genuine native/GGUF runtime failures within 60 seconds open the
  circuit for 10 seconds. Further failed recovery attempts double the
  cooldown up to 120 seconds. A completed successful native execution
  resets it. Rejected prompts, explicit cancellation, and SQLite replay
  do not increment the failure counter.
- `GET /v1/status` returns `inference_circuit.state` as `closed`,
  `open`, or `probe_ready`, with a bounded retry interval and no
  model path, prompt, exception string, API key, or token. During an
  open interval `ready=false`, with
  `model_readiness_code=local_execution_circuit_open`.
- New synchronous and asynchronous generation both fail closed while
  the circuit is open. Existing committed history, GET-only recovery,
  and exact idempotent retries are still readable without loading the
  model or spending another generation. A failed ticket is **not**
  advertised as a completed model result.
- This counter is intentionally memory-only. Restarting the process
  resets its local failure counter, **not** the SHA-bound model identity,
  SQLite receipts, canonical conversation, protected engine policy or
  operator deployment requirements. A device supervisor must enforce
  its own restart budget and crash-loop control.
- CPU/GPU pressure admission remains owned by the existing local
  resource fabric and llama.cpp execution guards. Circuit status
  is not a substitute for measured production GGUF and device proof.

The `tests/test_jeeves_inference_circuit.py` regression suite includes
a deterministic monotonic clock, sliding-window expiry, exponential
cooldown, real native/SQLite replay during an open circuit, actual
backend-error injection and cancellation non-escalation. These tests
validate execution-plumbing behavior, **not** model-language quality,
operator GGUF speed, independent protected-backend quorum or handset AI.

## 8. Whole-history SQLite and portable-backup custody

Every authoritative conversation read validates full transcript/receipt
order and all required modern native/GGUF execution receipts against their
saved revisions, model/tokenizer identities and output hashes. New Jeeves
HTTP outputs with mandatory runtime receipts are bound to **SHA-256 of visible
UTF-8 answer text**; any mismatch anywhere in that history is rejected.

Compatibility note: older standalone native ChatEngine generations use a
**token-sequence replay digest**, not SHA-256 of displayed text. Their rows
have no mandatory HTTP runtime-execution receipt and remain explicitly
unverified by the new text-digest rule. Do not retrofit invented native
attestations or break those historical conversations.

A missing, mismatched or retroactively attached receipt fails the *entire*
conversation load rather than only failing a GET for the individual damaged
turn. Jeeves must not use unverified earlier replies as context for another
model generation. Its SQLite integrity checks are self-consistency and
tamper-detection controls, **not** remotely signed attestation.

Forked and portable imported turns retain transcript/receipt consistency
but do **not** magically acquire a native execution identity for the new
session: their runtime receipt remains explicitly absent until a new native
generation occurs. An unverified historical row must never be relabeled as
having run through the trusted native backend.

A bundle checksum is unkeyed. It cannot authorize a model, supply protected
backend proof, or excuse a nested `output_digest` inconsistent with its
assistant text. The `tests/test_jeeves_durable_integrity.py` suite actively
mutates earlier SQLite runtime receipts and rechecksums portable envelopes,
checking that invalid histories fail closed while valid legacy, forked and
imported history remains usable.

## 2026 local execution custody: independent service-process safety

The standalone authenticated Jeeves HTTP service now uses an additional
**OS-backed, cross-process inference lease**. Each private SQLite workspace
has one persistent `<database>.inference.lock` sidecar. Before a **new** native
or GGUF generation, the service acquires a non-blocking exclusive operating
system lock. It retains ownership from the pre-generation request replay
check through model execution, SQLite commit and local receipt verification.
This is separate from the in-process admission counter and failure circuit.

- A concurrent service against the same private database receives **HTTP
  423 Locked** (or a failed asynchronous ticket with a stable sanitized busy
  category), **without executing a second model** and without mutating
  the conversation. Exact previously committed requests remain readable.
- POSIX uses a descriptor-backed `flock`; Windows uses `msvcrt`
  non-blocking byte-range locking. A process kill closes its descriptor,
  so it cannot leave a dead-process PID lease indefinitely blocking chat.
  Do not delete the lock marker during normal operations: another process
  could still hold the old inode, defeating exclusivity.
- Lockfiles must be owned private regular files with one hard link and an
  exact one-byte, nonsensitive marker. Symbolic/hard links, unsafe POSIX
  permissions, replacement of an inode while acquiring it, or unprotected
  shared parent directories fail closed. The marker contains **no prompts,
  credentials, model paths, process identifiers, or user conversation data**.
- The lock is **single-host and local-filesystem only**. It is not a
  distributed leader-election service or proof of correct NFS/SMB locking.
  Run the SQLite database and lock marker together on a trusted local disk.
  A different database may have a different local inference workload; this
  mechanism is not a global GPU scheduler or substitute for hardware
  resource admission.
- The operator's real GGUF HTTP qualification now also starts a
  **second independently authenticated localhost listener** on the same
  database. While one listener holds the kernel lease, a new synchronous
  turn through the other must fail HTTP 423 without changing any SQLite
  history. It then restarts the original listener and submits the **same
  previously denied request ID**; only this later admitted call may execute
  the second genuine native turn. The JSON report explicitly distinguishes
  `competing_local_service_inference_denied` and
  `denied_peer_request_committed_after_restart`. Both listeners run in
  one operator process; the separate subprocess-kill scenario remains
  covered by the adversarial unit suite, not by this GGUF operator test.
- The `tests/test_jeeves_local_lease.py` suite exercises independent
  in-process owners, a **real child process** holding the kernel lock,
  immediate recovery after killing that process, unsafe lockfile attacks,
  and an actual native model committing/replaying an answer after peer
  contention. The source CI includes these tests, but running them does
  not certify operator GGUF, protected bootstrap, Windows installer or
  disconnected-phone inference.

This is **fail-closed execution ownership**, not an invitation to start a
second unreviewed Jeeves model, bypass a held merge/release gate, or claim
a remotely hosted fallback exists.
