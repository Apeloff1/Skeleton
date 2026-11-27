# Functional verticals delivery — November 27, 2026

This draft implements the Jeeves → Dragon → Skeleton priority on current main,
including the relevant open-PR work. It preserves the distinction between a
usable source project, an observed native game, a running application, and a
qualified model or production deployment. The installation entry point is
[the draft quickstart](../install/VERTICALS_DRAFT_QUICKSTART_2026_11_27.md).

## Completion brief

Build an integrated creation application whose breadth survives actual use.
Prioritize Jeeves, then Dragon, then Skeleton, and improve shared model and
game-builder quality through their existing owners. Make each option meaningful:
typed input, validated semantics, an explicit effect, recoverable persistence,
and a readable result. Preserve the creator's words and unsaved work across
ordinary navigation, conflicts, delayed responses and explicit retries.

Deliver complete user journeys from a first launch through authoring, preview,
review, save, reopen, compare and export. Exercise owner and viewer boundaries,
lost acknowledgements, concurrent edits, cancellation, small screens and native
runtime failure. Reuse canonical application, inference, storage and compiler
contracts. Retain real regression assertions when reconciling other branches.
Publish cohesive draft increments with exact-source evidence and usable
artifacts; keep release, trained-model and competitive claims tied to observed
acceptance rather than counts of plans, catalogs or reference algorithms.

## Delivered behavior

| Area | User-visible result |
| --- | --- |
| Jeeves guided creation | Research, planning, creative, study and Studio journeys retain provenance, typed choices and atomic task dependencies. Cold authentication hydration and stable per-message Studio handoffs avoid duplicate goals while preserving distinct replies. |
| Forge parameter editing | All 500 maintained authoring operations have typed, lossless JSON controls, including nested objects and arrays, safe explicit references and an advanced repair view. Unsafe numeric tokens remain intact. Dirty navigation and new-project actions require resolving the current draft. Bounded Saga/Epic discovery now uses actual server metadata, closed generation filters and explicit preview/save; Continuity remains a separate namespace. |
| Forge save recovery | An explicit retry carries the original immutable request. A lost response can be recovered from the committed revision without applying steps or admitting a second write. Later queued edits survive; a newer peer head is read before the next save. Prepared candidates are never presented as committed success. |
| Dragon creation | Owned saved projects support immutable version comparison across design fields, briefs, citations and puzzle-board cells. Comparing revisions neither saves nor replaces the creator's unsaved draft. |
| Local native builder | Four genre starters—shooter, platformer, roguelike and sequence puzzle—combine with difficulty, theme, encounter, speed and objective choices in an exact reviewed brief. Durable jobs, original-request recovery, private history and verified ZIP download use the existing local workspace. Explicit retries stay available during observation, and stale poll responses cannot overwrite a newer receipt. |
| Native play and progression | Required builds verify actual Godot input after boot. The maintained runtime exercises movement, objectives, pause/restart and file-backed progression save/load. Records bind the complete accepted design, use a closed bounded format and refuse corrupt, oversized or foreign data. They are progression records, not mid-level world checkpoints. |
| Shared runtime | Grounded bounded local proposal repair, restored chat evidence controls, real environmental approval guards, bounded learning explanations, finite multiplayer state, grant validation and bounded rollback histories close concrete runtime gaps. |
| Studio and Expedition | Shipped catalogs remain separate from supplemental reference solvers. Immutable world indexes remove repeated whole-edge reconstruction while preserving serialization, source digests, deterministic paths and caller isolation. |

The authoring catalog, expedition catalogs and numeric address spaces are
different kinds of options. Their sizes are not counts of polished shipped
games. Source-only and proposal-only surfaces retain those labels.

## Verification and artifacts

The accompanying delivery receipt records exact commits, SHA-256 identities,
artifact locations and final browser outcomes. Evidence is deliberately scoped:

- The complete frontend TypeScript check and zero-warning lint pass. The
  bounded complete Jeeves client lane executes **373 tests**, with no skips.
- The final configured backend lane executes **277 tests**, including actual
  authenticated disposable Mongo persistence, acknowledgement recovery, Epic
  audits, all twelve recipe namespaces and the local native-builder contracts.
  Every selected case executes; none are skipped.
- **82 distinct strict native/profile/quality checks** execute with installed Godot
  4.7.2 and no missing-engine skips. Four actual genres and seven platformer
  speed profiles are covered. A bounded input-only landing controller fixes a
  false rejection of a playable speed-240 platformer without changing game
  physics, quality thresholds or the requirement to win and verify saves. A further
  actual local browser journey observes six successful Godot processes and a
  file-backed `save_verified: true` receipt.
- Additional targeted lanes exercise multiplayer authority (**162 tests**),
  full Expedition/Studio behavior (**132 tests**, plus ten new index regressions),
  canonical registry/environment/learning behavior (**85 tests**), and real
  Dragon archive/instruction/temporal guards (**80 tests**).
- Fresh actual browser journeys pass **8 guided Jeeves**, **10 Dragon
  comparison**, **11 typed Forge/save-recovery**, and **8 durable source-export**
  checks. The source-export flow creates 25 real builds and recovers the
  original beyond the latest 24. The separate local native journey passes
  **9 checks**, with exactly two explicit identical POSTs, one admitted job, one
  declared proposal fixture and six actual Godot processes. HTTP, databases,
  compiler output and downloads are real; explicitly named production-admission
  and structured proposal fixtures do not qualify trained inference.
- All 183 AI-tree mappings and independent ownership checks pass after reviewed
  source reconciliation. Architecture, construction, interfaces, state,
  bootstrap, implementation dossiers and product inventory have their own
  final receipts; no release or cutover status is promoted by these checks.

Four standalone Godot projects are delivered in `verified-godot-starters.zip`: a
shooter, platformer, roguelike and sequence puzzle across four themes and three
difficulty settings. They contain 132 generated source files plus instructions
and receipts, and can be played without Python, a model or application services.
All four were freshly built with required native proof on the corrected source.
The ZIP is 183,306 bytes; SHA-256
`54216b1598115ab2445a902733e949aa55a3ca348a8e45ee47f53fe49a86b63a`.

The browser package is a guarded Expo export. Its accompanying installation
receipt records the exact file count, size, SHA-256 and committed frontend tree.
The exporter completes through supervised post-export exit; this does not
establish a normal exporter shutdown. Actual HTTP checks serve the root, setup,
authoring route and hashed scripts. The package still requires the configured
backend to perform authenticated application operations.

## Installation and readiness

The quickstart uses the existing installer and local workspace commands. Source
and browser packages exclude operator credentials and model weights. The
verified starter projects can be opened directly with Godot; generating new
model-proposed games requires a compatible operator-provided trained GGUF and
llama.cpp executable. No trained GGUF was available in this environment.

The assembled backend was actually started against authenticated Mongo:
`/health/live` and `/health/startup` returned 200, authentication remained
enforced, and the declared background tasks drained on shutdown. Readiness
remains 503 because the disposable configuration has no provisioned builds vault;
the optional local AI provider is independently unavailable.
The default Compose provider requires externally administered trusted guard
components and the documented cross-process shared-epoch integration; the
optional full-profile Chroma path also remains unqualified.
These are material installation limits, not successful production acceptance.

No physical-device, trained-model-quality, production-release or competitor
superiority claim is made. Draft [PR #6004](https://github.com/Apeloff1/Skeleton/pull/6004)
contains the reviewable implementation and current-source integration record.
