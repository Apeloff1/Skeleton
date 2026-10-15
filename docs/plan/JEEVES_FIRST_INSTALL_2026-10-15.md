# Jeeves first install, chat and Dragon capture continuation

This continuation makes the existing application operable from a fresh checkout
and connects its AI and crawler through the canonical owners. Earlier work could
start with transient login secrets, claim AI readiness from configuration alone,
lose chat execution identity during recovery, and expose crawler knowledge without
an application capture lifecycle. The implementation addresses those concrete
failures. It does not mark the wider AI masterplan complete.

The operator guide is [First install: AI chat and Dragon web capture](../ai/FIRST_INSTALL_AI_AND_CRAWLER.md).
Exact measured results are maintained in
`machine/ai_first_install_session_evidence_2026-10-15.json`. Native studio and
two-turn model-to-app evidence remain separately preserved in
`machine/ai_game_studio_session_evidence_2026-10-14.json#runtime_continuation`.
No automated tests were authored or run, following the user's instruction.

## Installation and activation

The existing installer now installs the actual application metadata/dependencies
before importing the full package. Setup generates stable private Mongo, engine
and authentication credentials, preserves valid existing values and repairs
placeholder configuration. GameForge's authentication secret is configured under
the exact setting its canonical owner reads. Optional administrator bootstrap
uses explicitly supplied operator credentials; new public registrations retain
their viewer role.

Minimal startup retains mandatory authentication and storage indexes while
deferring bulk generated libraries, launch-time training and unrelated downloads.
Docker Compose remains the supervisor, with existing service/state owners and
durable engine execution, quota, tool and governance paths. No browser component
can run shell commands, set credentials, install binaries or activate a model.

`app doctor` observes host, configuration, services and canonical model inventory
separately. Engine configuration does not establish provider availability. Local
mode can boot the platform with a safe non-dispatchable descriptor when weights
are absent or invalid; the ordinary registry constructor still fails closed.
The descriptor has no invented model identity and cannot fall through to hosted
inference.

An explicit operator provisioning script acquires or reuses exact pinned Qwen
weights and a compatible llama.cpp runtime. Downloads require an explicit flag;
the offline path uses the exact same byte/digest requirements. Bounded copying,
isolated finite download workers, archive member and expansion limits, regular
library materialization, create-only files and canonical deployment admission
precede activation. Portable relative paths support the read-only engine model
mount. Public artifact permissions work with the existing non-root container.
The engine image uses a compatible glibc base for this CPU runtime.

The installer creates the default operator-owned empty model directory before
Compose binds it. Provisioning can exclusively claim this safe empty directory
and subsequently verify a complete installation without overwriting it. Actual
empty-directory preparation and verified reopen retained 42 manifest-listed
files, including 40 runtime files, with 710,843,625 measured bytes.

## Canonical chat

The backend projects the current engine's actual configured models and conservative
chat limits. Exact provider/model selection and supported temperature bind to the
immutable execution request. Explicit model selection cannot silently switch to
a fallback. Automatic routing retains only the declared active/fallback policy.
Unsupported sampling and insufficient context fail before provider dispatch.

The first durable execution checkpoint binds the requested tenant/command to
the exact ordered provider routes, local weights, runtime/profile/manifest,
verifier and implementation identity. Unfinished work compares that binding on
resume and around dispatch. A changed activation or unbound legacy checkpoint
fails closed; completed historical results remain readable. Responses must match
an actual configured provider/model pair, including a declared successful
secondary route. Local inference also checks the complete rendered input and
output budget before execution and drains cooperative cancellation before
releasing physical work.

A fresh chat turn appends its canonical USER message and exact prepared engine
command together under the existing governed conversation authority. The stored
command binds operation, execution, source context, idempotency and resource
budget. Recovery verifies that envelope rather than rebuilding timestamps or
inventing a new attempt. Current owner, writable tip, context dependencies and
command lifetime are checked again before continuation.

Conversation and turn collections decode BSON dates as aware UTC. New lease
timestamps are normalized to BSON milliseconds before identity issuance. Long
sessions use bounded complete active lineage with explicit count/byte, missing
parent and cycle failures; the former silent first-500 truncation is removed.
Public transcript projections exclude the private prepared command payload.

Deferred admission, status, cancellation, exact resume, canonical final acceptance
and actual durable transition streaming share the same identities. Event replay
checks operation, sequence and prior digest. The stream uses real disconnect
events through the existing bounded-body middleware. Buffered local providers
produce final text and transitions; the interface does not invent token deltas.

The frontend binds a conversation before admission and saves the binding before
following events. A reconnect can resume the same server turn. Explicit Stop asks
the server to cancel; local detachment leaves durable work intact. New cache keys
require fresh server-verified account identity, clear derived state on account
change and do not read or delete legacy global cache bytes. Archive, title CAS,
erasure and complete JSON/Markdown export use canonical server authorities.

## Durable Dragon capture and AI grounding

The existing canonical crawler now has a bounded operation facade. Snapshots bind
scope, consent, immutable request and implementation identity; retain complete
frontier/robots/deduplication/source state; and preserve cumulative measured and
conservatively reserved usage. A dispatch reservation is committed before network
I/O. A failed final checkpoint cannot turn an uncertain request into free work.

The transport preserves trusted proxy/CA configuration, public destination checks,
robots policy, redirects, response limits and total deadlines. Bounded isolated
DNS resolution prevents an uninterruptible host resolver from outliving the
physical worker fence. Proxy-origin connection ownership remains explicit;
the application does not fabricate origin-peer pinning.

The backend stores operation snapshots in the existing CORE_DB Mongo authority.
Scoped version CAS, immutable operation keys, server-clock lease epochs and
physical slice credits fence overlapping workers. Request-driven slices run
finite work and drain the actual thread before capacity reuse. Expired work
reopens from its last committed snapshot. The app supports create, inspect,
pause, resume, cancel, paged sources/events, exact content exports and erasure.

Editor/admin role and explicit capture/use consent gate acquisition. Read and
export paths preserve exact owner and source permissions. Captured text is
unreviewed external evidence. It does not automatically become reviewed Dragon
Academy knowledge, training permission, XP, a verified claim or a policy upgrade.

Chat can request a bounded lexical query against its owner's actual retained
captures. Exact offset-anchored passages enter the existing ContextCompiler as
untrusted retrieval evidence. Source, passage, request and consent identities are
frozen and revalidated before dispatch, resume and transcript publication.
Explicit canonical memory references retain their original owner, version and
lifetime checks. Erasure or consent withdrawal prevents downstream context reuse.

## Qualification and operation

The retained workloads distinguish acquisition, activation, model execution,
application command execution, replay and quality. For example, a successful
first chat transport produced only unfinished model reasoning at a 64-token
budget; that result is preserved rather than presented as a useful answer.
The known model profile and acceptance behavior are refined against actual
subsequent inference. A completed studio inspection workflow also retains
`goal_satisfaction_verified=false` despite valid model and command receipts.

The final Qwen3 nonthinking profile produced a useful one-sentence answer about
the captured Example Domain page and cited `https://example.com`. The canonical
turn retained one actual provider receipt, nine durable stream transitions over
two connections, identical replay/resume identities and a verified two-message
Markdown export. Erasing that capture then made its source unavailable and
blocked a same-thread follow-up with `chat_crawler_source_withdrawn`, before any
new user message or model request was admitted.

Actual crawler acquisition retained two public documents, four requests,
29,491 measured bytes and seven offset-anchored search hits. The authenticated
application capture separately completed create, pause, resume, source/event
inspection, both export formats, cancellation and idempotent erasure through
real backend/Mongo authorities. These are measured capture operations, not
model training or reviewed-knowledge promotion.

The final production web export contains 294 files and 188 HTML routes. Actual
Chromium inspection observed hydration, current readiness, guarded guest access,
successful account login, the owned conversation library, the configured local
model selector and the captured answer on desktop and mobile, with no JavaScript
exceptions. An earlier compiled export failed at browser hydration because of
an untransformed dependency `import.meta`; its failed evidence is retained. The
supported Expo Babel transform corrects the final artifact. The production
Nginx ingress sends backend-owned versioned conversation routes to the backend
and disables buffering for chat transition streams.

Required construction/architecture/interface/provider/enterprise validators,
source ownership, Python compilation, scoped lint, TypeScript and the production
web export are recorded separately from those operational workloads. No test
framework is used. Neither configuration nor a web build proves model quality,
all-console compatibility, original-game superiority or 100,000-run endurance.

Recovery keeps original commands, counters and source/authorization history.
Operators restore the existing Mongo and engine state volumes together under
their existing retention/governance rules. Source changes do not authorize
silent historical journal repair. Reverting application code requires attention
to candidate versioned snapshots and newer execution records; old code must not
be pointed at incompatible writable state. Stop active workers and preserve
their receipts before changing runtime or model activation.

## Integration with current main

The earlier PR was already merged and its feature branch removed. This
continuation is applied against main commit
`020fa731fd3a295aa0fbc98f219a00503c788742`, preserving the newer application and
native-training capabilities rather than replacing their files. The integration
retains governed chat attachments, edits/regeneration, searchable conversation
history, exact lease tokens and graceful shutdown; neural document training;
Dragon native/world delivery routes; native checkpoints, rewind and controller,
video and PCM provenance; and existing CLI entrypoints.

The canonical provider resolver accepts both existing prepared-command policy
key formats and rejects conflicting dual values without rewriting historical
request bytes. Bounded attachments and explicitly consented Dragon projections
keep their existing source owners and receive the same prepared-context identity
and withdrawal checks. The existing governed chat client remains available; the
first-install session adapter uses the same backend conversation/engine authority.

Pre-integration container and browser receipts keep their original source pins.
Final integrated source, browser and service observations are recorded separately
in the machine evidence, so an earlier successful run cannot attest changed code.

The final combined application completed a real public capture and one local
grounded chat. Both stream APIs returned nine digest-linked transitions; replay,
resume and the two-message export preserved the same canonical result. Source
erasure then prevented a new same-thread request before admission. An initial
fresh-turn rejection exposed the difference between a prospective current USER
and persisted history. The correction validates that exact current message and
its compiled digest, while retaining strict checks for every historical ID. The
same unchanged thread, request and operation key subsequently completed; the
failed receipt remains retained.

The final observed web archive contains 306 files and 199 HTML routes, with
SHA256 `9d89e64b0d9d3658fa854f83102f2f1876f7e73309e4696cf40fc3ad2c8fbbfe`.
Real Chromium recovered the exact answer in both chat views on desktop/mobile,
verified account scope and model readiness, and recorded zero JavaScript or
console errors. Screenshot inspection additionally corrected a companion panel
obscuring the composer and a compressed mobile crawler heading. The separate
reviewed Dragon practice/companion store remains optional and unconfigured;
its unavailable state is shown without inventing knowledge or training.

Fresh canonical glibc engine and production backend images, a fresh Mongo volume
and the final host Expo export packaged into the pinned production Nginx runtime
also completed installation qualification. All four services were healthy.
Platform, configuration and service doctor checks passed both without weights
and after activating the pinned read-only model. Actual administrator/viewer
tokens survived backend restart; same-origin chat completed genuine container
inference and stored its assistant in Mongo. Crawler controls and source hashes
were independently observed through that stack. The container Node builder was
not rerun: the real host Expo export, exact served JavaScript and production
Nginx image identities are recorded explicitly.

Required source gates passed, including whole provider-boundary validation and
179 governed file-tree mappings. Restoring 49 missing/stale declared mirrors and
declaring 12 already-existing main training overlays preserved current main's
capabilities. Changed Python ownership, AST and compilation cover 123 files;
lint comparison distinguishes existing canonical diagnostics from authored
changes. No automated tests were authored or run.
