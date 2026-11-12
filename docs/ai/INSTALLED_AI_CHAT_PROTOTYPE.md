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


## 9. Executable localhost Jeeves self-check (real model, not a status ping)

The authenticated same-origin desktop browser exposes **Run genuine local inference
self-test**. The control is unavailable until local model admission reports
ready. When clicked, it creates a **real new SQLite conversation**, submits one
bounded asynchronous local-model request and waits for its durable terminal
receipt. The check then uses WebCrypto SHA-256 to hash the exact assistant UTF-8
text, compares the stored execution digest and active model identity, and
re-reads the saved SQLite conversation. Only a genuinely committed answer
with matching text, revision and native execution sidecar can show a qualified
local inference check. A nonsecret JSON report can be downloaded.

An unavailable model, timeout, cancellation, bad digest, missing receipt,
changed token or lost history produces **NOT QUALIFIED**, not a fabricated
response. If delivery is uncertain, the original request ID is retained for
the existing Check status / Retry original turn workflow; the browser never
creates an unrelated replacement request silently. The live check does not
certify model reasoning quality, independently protected app bootstrap,
operator-owned GGUF weights on another host, physical handset operation or
release readiness.

## 10. Dragon-to-Jeeves local evidence bridge (actual user workflow)

Dragon's guided capture pilot exports a bounded JSON `skeleton.dragon.
owner_evidence_bundle.v1` with either provenance-only metadata or historical
per-source authorized JSON copies. The local Jeeves browser now has an
**Import approved Dragon evidence (local only)** panel. It supports **only**
the authorized-source-body mode and requires:

1. A 1-byte to 2-MiB explicitly selected JSON file, source count 1–8,
   stable session identity and revision, and all publication/training/release
   flags explicitly **false**.
2. Per-source SHA-256 of the exact historical export bytes, matching
   exported source/capture digests, valid policy version, bounded UTF-8
   source text (up to 225 kB), and historical source-use/freshness fields.
   The user chooses a Unicode-code-point start and 1–3000-character excerpt;
   the reviewed excerpt is capped at 12 KiB and must match the preview.
3. A full on-screen untrusted-text preview and a **fresh, manually checked**
   owner approval checkbox for the exact selected excerpt. Switching
   excerpts removes that checkbox grant.
4. Explicit `POST /v1/advisory/ingest` through the **existing authenticated
   localhost service** with text and source digests. The server separately
   verifies the exact observation SHA-256 before storing the text under the
   active model's private SQLite knowledge authority. An exact duplicate
   returns the existing document instead of silently creating another.
5. An explicit separate **Include local evidence** option on a subsequent
   conversation turn. Import never auto-invokes inference or promotes
   captured source instructions to a system/developer/tool role.

**Security limitations:** Dragon bundle checksums authenticate equality of
bytes, not the source publisher or user's current rights. A saved bundle is
a historical snapshot and could be manipulated by its holder: local Jeeves
cannot remotely revalidate Dragon's live tenant authority, robots, legal
license, takedown state or freshness. The user must independently recheck
permission before approving each excerpt. The text remains explicitly
untrusted in the model context, and the primary model stays local Jeeves.
No raw media decoding, remote service, automatic training, publication,
unsandboxed tool action or developer-level prompt elevation occurs.

The `tests/test_jeeves_live_local_advanced.py` acceptance suite now
checks the actual local model + SQLite receipt semantics, the browser
self-check and its Dragon UI wiring, and an actual reviewed crawler
observation into SQLite without another generation.

## 11. Full-conversation context fidelity and local preflight (implemented)

The Jeeves browser now defaults to **Require entire conversation context**.
This is a real execution policy, not a cosmetic indicator. The previous
`OfflineAISession._request` behavior conservatively trims oldest
user/assistant *pairs* until the model context budget can fit the request.
The complete canonical SQLite transcript remains intact, but an earlier turn
might not have been supplied to the model. That behavior remains supported
**only through explicit bounded-recent opt-in** in the browser.

An authenticated read-only `POST /v1/sessions/<id>/context-preview`
accepts `message`, `max_output_tokens`, `grounded` and
`require_full_history`. It uses the actual history-to-prompt renderer and
current model's admitted context and output budgets. The result reports
full/retained/omitted message counts, total input/output estimates, real model
digest, SQLite revision, strict-policy admissibility and whether the accounting
is **exact native-tokenizer** or **conservative GGUF UTF-8 bytes**. Grounded
previews use the same bounded local reference retrieval and manifest
construction as an actual grounded model turn; absent matching evidence
refuses the preview. No model invocation, remote provider, SQLite write,
privileged approval or automatic summary is done by this endpoint.

When strict history is required, both asynchronous and synchronous native
generation use the `require_full_history: true` request bit. The execution
adapter now **refuses before inference** if even one older pair would need
trimming; returning a superficially successful partial-context answer is
forbidden. When the user consciously unchecks the box, bounded-recent
generation may continue with the previous deterministic pair trimming,
without ever deleting historical SQLite conversation rows. In either case,
restarting/replaying a committed request returns the exact historical receipt.
The policy bit is domain-separated into the idempotent request digest, so
reusing an ID while switching between strict and bounded modes is a
deterministic conflict, not a hidden changed-policy replay.

A **Preview context** button displays the current counts and shows a
warning if an older pair would be omitted. A strict send performs a fresh
read-only preflight before scheduling the actual turn. The generated turn
**also independently revalidates** the strict policy; the browser preview
is not an admission token and cannot bypass a concurrent conversation
revision or model change. Older API clients continue to use the legacy
bounded mode until they explicitly send `require_full_history: true`.
The operator may adjust the output budget, shorten an input, start a fork
or explicitly allow trimming; no automatic model substitution occurs.

**Limitations:** this is an exact token count for the source-native tokenizer,
but GGUF `llama.cpp` may perform a different final tokenizer/context check
and refuse after the preview. Full history fitting says nothing about
reasoning correctness, language quality, publisher rights or actual
hardware acceptance. No automatic lossy conversation summary is represented
as having preserved the whole context. The standalone `OfflineAISession`
still has an ephemeral 16-message display cache; the durable HTTP
`DurableOfflineAISession` re-opens the entire integrity-verified SQLite
history before calculating each new model request.


### Exact Unicode passage custody in Dragon imports

A reviewed Dragon excerpt now includes the optional, strictly validated
`source_span: {start, end, unit: "unicode_code_points"}` in the
`skeleton.jeeves.advisory.v1` ingestion request. The client extracts a
bounded passage using Unicode code points (not UTF-16 JS code units) and
requires a fresh explicit checkbox grant after each source/offset/length
change. The local backend refuses wrong types, negative/inverted/too-large
bounds, a mismatched `end-start` versus actual Unicode passage length,
non-crawler modalities, unexpected keys and empty observations.

The canonical SQLite advisory document now includes the source claim,
the exact **caller-declared** offset range and the independently verified
SHA-256 of observation bytes. This is provenance/context, **not** a claim
that the local model independently re-fetched or verified the historical
Dragon source. The structured return labels the authority precisely:
`source_span_authority: caller-declared-not-source-reverified`. The browser
checks the echoed range and authority before showing success. Replaying
the identical reviewed advisory reuses its content-addressed record; a
different range changes its canonical content digest. This never
creates a model turn, grants publication rights or revalidates old
external capture consent.


## 13. Inspect the exact local citations before grounded model inference

The Jeeves authenticated `POST /v1/sessions/<session>/context-preview`
endpoint now returns a bounded `grounding_preview` object when
`grounded: true`. It includes a model-bound source-context SHA-256, exact
question SHA-256 and up to two independently validated local citations:
model-scoped document ID, content SHA-256, chunk ID, exact Unicode character
coordinates, finite selected passage and passage SHA-256. It is **read-only**
and makes no model request, storage mutation or network-provider call.
Non-grounded previews return `grounding_preview: null`.

The browser exposes a collapsible **Local grounding passages selected by
preview** panel. It validates the schema and coordinates, independently
checks each passage SHA-256 with browser Web Crypto, and renders every untrusted
passage with DOM `textContent` rather than interpreting it as HTML.
Account disconnection, session change, prompt edit, grounding toggle and
context-budget change clear prior source previews so stale text is not shown
as fresh source evidence. The operator can inspect the exact citations
before submitting a real local-model question.

This remains a **preflight snapshot**, not an execution receipt or a promise
that documents cannot change before generation. The actual local model turn
constructs a fresh evidence manifest, and the canonical SQLite transcript
stores the citations that were *really supplied* with the generated answer.
No preview automatically authorizes reproduction, publishing, training or
external-site access; Dragon historical sources remain untrusted until
separately reviewed. The test suite compares inspected source offsets with
their saved SHA-bound documents and confirms the subsequent real native
inference receipt retains the same citations when nothing changes.


## 14. Select exact local reference documents for the next model turn

The authenticated Jeeves browser now exposes **Use** checkboxes beside real
local references. An operator may select 1–8 document IDs to restrict
manual reference search, the next grounded context preflight and the actual
native/GGUF model turn. All selected IDs are validated against the exact
model-and-tokenizer-scoped, SHA-checked SQLite document/chunk authority.
If a selected source disappears, is withdrawn or belongs to a different
local model identity, the request fails **before generation** instead of
silently broadening to other documents. No new model, provider, network
request or external crawler is involved.

The existing `/v1/knowledge/search`,
`/v1/sessions/<id>/context-preview`, synchronous `/turn` and asynchronous
`/turns` endpoints accept optional `document_ids` arrays, rejecting
duplicates, malformed IDs, excess cardinality and selection on ungrounded
turns. Without an explicit selection, legacy local reference search remains
unchanged; the browser displays that all locally saved references are in
scope rather than pretending a source has been chosen.

Selected IDs are sorted, bounded, and domain-separated into the **grounded
idempotency request digest** before applying strict-history policy. The
source citation manifest and the final SQLite generation receipt use this
same scope-bound digest. Reusing a request ID for a different document set
or switching back to unrestricted search must never replay it under an
unacknowledged new source policy. A source selection change invalidates
the read-only preview. During a conversation switch or explicit lock the
source picker is cleared; unknown/deleted IDs are pruned on owner-authenticated
library refresh. No document IDs or private content are persisted in
browser localStorage/sessionStorage.

A selected document is still *untrusted grounding data*, not a system
instruction, current publisher-rights certificate, factual verification
or permission to train/publish. The genuine native tests cover source-scoped
search, SHA-bound preview, real inference and SQLite commit/replay, removal
during use, invalid arrays, async tickets, and the browser contract.
Actual operator-owned GGUF quality, device and release checks remain separate.


## 15. Fail-closed local document scope after deletion and account changes

The local Jeeves browser now makes a critical distinction between **explicit
selected-only grounding** and **explicit all-references grounding**. Selecting
even one local reference switches into selected-only mode. Deselecting the
last reference leaves the mode empty and **blocks** grounded preview and
generation; it never implicitly widens the question to the whole library.

A deleted, withdrawn or inaccessible selected local document remains as a
tombstoned selection in the current authenticated tab. The source-inventory
refresh only updates the currently accessible IDs; it no longer clears
unavailable selections. A prominent warning explains that the next grounded
turn is blocked and offers an explicit operator action to reselect an
available source or return to the complete private library. No source
content is copied into another model or third-party service.

A dedicated **Explicitly use all references** control is the only interaction
that widens selected-only grounding to unrestricted local retrieval. Switching
conversations preserves the existing restriction. Locking the workspace
clears both the restriction and its source IDs as an intentional
authentication boundary; reauthentication never silently grants an older
source approval. Source-list responses are fenced by the active connection
epoch and inventory request sequence, so a late refresh cannot reset a
newer selection or another account's view.

Both context preview and actual inference compare their captured
source-selection version after asynchronous work. The backend independently
requires every selected ID to be present in the model-scoped, SHA-verified
SQLite source collection and maintains source-selection idempotency
separation for the real native model receipt. The source picker can never
bypass this server-side gate. The genuine native tests exercise a deleted
selected document with another otherwise usable document still present:
no model generation, answer or SQLite history mutation may result.

Limitations: client source-inventory reads are not an atomic transaction
with generation, so the actual native turn always independently checks
the selected sources. The system cannot revoke already-exported Dragon
source text or infer publisher rights from source presence.


## 16. Real locally verified media advisory ingress (implemented)

The installed browser now has a **Review local image, audio or video for
Jeeves** interface. It accepts a user-selected **PNG, JPEG, WebP, WAV,
FLAC or MP4** file of no more than **4 MiB**, optionally previews that
file using a page-owned `blob:` object URL, and computes the exact file
SHA-256 with browser Web Crypto. The user supplies their own explicitly
reviewed textual caption, transcript, or frame annotation, which remains
**untrusted grounding data** rather than new privileged instructions.

The **real authenticated loopback** `POST /v1/advisory/ingest` uses the
existing `skeleton.jeeves.advisory.v1` contract with optional
`media_type` and `media_base64` fields. A finite 6 MiB HTTP body budget
enforces the size boundary before JSON parsing; the dedicated decoder enforces
canonical Base64, a 4 MiB binary limit, recognized MIME/modality pairing,
and basic container signature consistency. The server independently
calculates SHA-256 of the exact decoded bytes and compares it to the
submitted source digest before any SQLite writes. One incorrect digest,
unreviewed observation, mismatched media type, malformed container header,
noncanonical encoding, oversized upload or unknown field refuses the
**entire advisory**. The client independently confirms the returned source
digest, MIME, byte count, owner-review contract and **no inference** status.

**Privacy and content guarantees:**
- Raw media bytes are never placed in SQLite reference text, model prompts,
  conversation history, auxiliary model state, or the local execution receipt.
  Only the human-reviewed observation, content digest, media-type metadata,
  source-byte count and explicit *container-header-only* qualification are
  stored under the existing private model-scoped content-addressed library.
- The server does not perform OCR, speech-to-text, video decoding, semantic
  analysis, caption generation, or outbound provider calls. The browser can
  display local media for the *human* with native browser viewers, but
  these are never interpreted as an AI decoder or a second primary model.
  A recognizable container header does not certify the rest of the file.
- Source provenance is upgraded from
  `caller-declared-not-media-verified` to
  `server-verified-transient-source-bytes` **only** when the original
  raw media bytes were actually inspected. Legacy text-only advisories and
  separately approved Dragon excerpts retain their previous honest
  caller-asserted source authority.
- Media preview object URLs are actively revoked when the selected file
  changes, the account locks, or the page closes; no token, raw file, or
  observation is persisted to browser storage. Strict CSP allows
  `img-src 'self' blob:` and `media-src 'self' blob:` for local user files
  while retaining `default-src 'none'`, same-origin fetch/script policies,
  no remote media endpoints, and frame embedding refusal.
- A successfully admitted observation **does not generate a model reply**.
  The operator must separately select it as a local reference, review
  selected grounding citations, and initiate a model turn. Only the
  installed **Jeeves primary local model** may generate that answer, with
  source-scope, strict-context and SQLite replay controls enforced anew.

**Qualification:** `tests/test_jeeves_media_advisory.py` checks six
supported headers, source-digest substitution, invalid Base64, malformed
media, MIME/modality mismatches, oversized input, explicit approval,
authenticated HTTP denial, real SQLite document storage and duplicate
reuse, the legacy crawler/text authority boundary, and real localhost
Content Security Policy. The exact-head Jeeves workflow compiles the new
module and runs these tests alongside native transformer and backend E2E.
An independently supplied production GGUF, media codecs/decoding quality,
Windows 11/WSL2, Apple Metal and physical devices remain separate
non-waived release qualification requirements.
