# Offline AI workspace implementation — 2026-10-13

Implementation candidate, continuing the recovery work in PR #3780. The operator
requested an hour of direct implementation and **no tests**. No test suite or
application acceptance probe was run for this batch. This is not a whole-app
completion or model-quality sign-off.

## Implemented

- Authenticated loopback AI requests can run in a background worker with a bounded
  status ticket, cancellation acknowledgement, explicit retry and durable replay.
  Compatibility synchronous clients use the same single-worker admission fence.
- Browser polling backs off and pauses without silently generating again. Lock
  clears in-tab credentials and content; reconnect can find an active request.
- Browser conversation search, pagination, previews, optional instructions,
  per-turn branches, private JSON backups, Markdown exports, copy controls and
  per-session in-memory drafts are connected to the existing SQLite authority.
- Reference files support batch import, verified original-text inspection/download,
  source search and removal. Shared file admission remains bounded and local.
- The desktop exposes model preparation, conversation search, instructions,
  output budgets, grounding, reference import/search, original-request retry,
  source excerpts, citation auditing and readable text copy/export. Browser layout
  keeps the composer reachable and uses a library drawer on small screens.
- Terminal chat has recoverable command errors, session switching, branching,
  references, JSON backups, Markdown exports, adjustable budgets, interrupted-turn replay and one-shot
  request IDs. JSON mode emits structured command events.
- `app prepare-local-model` creates a private pinned deployment from existing
  GGUF and llama.cpp files; it never overwrites a manifest, downloads a model or
  executes the runtime. `app chat` and `app serve-local-ai` reuse current owners.
- The Expo Jeeves screen projects the existing engine provider and free-tier
  status, distinguishing local generation from configured providers and extraction.
- Canonical reads can share a SQLite snapshot across transcript and source records.
  If another process wins an identical request during inference, the losing
  execution is not presented as the committed answer.

## Build work

- Python compilation succeeded for the changed Python modules.
- Embedded browser JavaScript parses successfully with Node's syntax compiler.
- Pinned Yarn dependency installation and repository postinstall patches completed.
- **Full Expo web export succeeded** and produced `frontend/dist`.
- npm's strict resolver rejected the repository's existing `expo-three` / `three`
  peer range. The repository specifies Yarn; its frozen install completed with
  peer warnings. No dependency or lockfile version was changed to force resolution.
- Expo emitted existing Three loader resolution warnings and force-exited after
  reporting a successful export. A successful bundle is not browser/native/runtime
  acceptance evidence.

## Construction obligations

This batch extends VOL-042's existing product shell and the declared local model
runtime. `machine/manifest.json` records the surface and authority bindings.

| Level | Implementation or remaining boundary |
| --- | --- |
| L00 Ownership | `skeleton/app` owns presentation/adapters; `LocalInferenceEngine` owns model execution; `OfflineChatStore` owns durable history and receipts. |
| L01 Dependencies | Existing Python standard library, local runtime and Expo stack. No provider SDK, hosted fallback, service or new runtime root. |
| L02 Contracts | Additive local ticket/search/document-read routes, shared snapshot reads and operator model-preparation command. Existing sync route remains available. |
| L03 Authority | Tickets are ephemeral projections. Model/tokenizer-bound SQLite receipts and immutable source records remain authoritative. |
| L04 Control flow | Validate/admit, execute, settle cancellation or commit, then hydrate saved history. A late cancellation cannot replace a committed result. |
| L05 State | Maximum 32 tickets; one active generation per server instance. No new tables or independent durable queue. Other processes remain subject to SQLite commit conflicts. |
| L06 Privacy | Authenticated numeric loopback, same-origin assets, no browser credential persistence. File imports are bounded UTF-8; content is rendered as text. Backup exports remain plaintext private records. |
| L07 Recovery | Original IDs/parameters, durable replay, restart/eviction messaging, explicit retry, clipboard/file errors, interactive command recovery and closed-window cleanup are implemented. Not acceptance-tested in this batch. |
| L08 Observability | Ticket state/timing, model/context limits, actual provider status, source IDs and citation audit status. No prompt or bearer-token logging. |
| L09 Economics | One active local HTTP generation, bounded tickets/files/context, controlled polling, no automatic generation retry. Separate processes can spend duplicate compute before a CAS/replay conflict; no global compute-once guarantee. |
| L10 Evaluation | Compilation and web export only. No runtime tests, model evaluations or acceptance results are claimed. |
| L11 Deployment | Existing package/server/frontend delivery paths. Model preparation uses private create-only hard-link publication on the destination filesystem. Revert the implementation commit to roll back; existing SQLite tables and backups remain compatible. |
| L12 Operator controls | Choose/pin local artifacts; select token/database/port; set budgets/instructions; inspect evidence; cancel/retry; search/branch/export/import/delete. |
| L13 Exit | Implementation candidate. Full acceptance, real trained-model execution and applicable exact-head gates remain unverified. |

## Material remaining work

- Real trained GGUF execution and answer-quality evaluation on target hardware.
- Windows desktop/installer and mobile browser interaction acceptance.
- Production-equivalent engine/Mongo/authenticated Jeeves journeys.
- Full application feature inventory and completion criteria. This patch does not
  establish a defensible app-wide completion percentage.
- Existing architecture and independent qualification gates, when testing is
  authorized again. No gate is relabeled as passed by source edits or compilation.

## Operations and rollback

See `docs/ai/OFFLINE_NATIVE_CHAT.md` and the README's standalone local-AI quick start.
A prepared manifest records absolute local artifact paths. The installed runtime,
its libraries, sufficient hardware and trained weights remain operator prerequisites.
Runtime model identity is still checked on use.

Stop the local server normally before reverting so active cancellation/commit work
can settle. Reverting removes new UI/API features without a data migration. Saved
turns, reference documents and earlier bundle schemas remain under the existing
owners. New model manifests continue using `skeleton.local_model.deployment.v1`.
