# Jeeves — Whole-Application Capability Atlas & Governed Runtime

**Date:** 2026-10-13 (Europe/Oslo). **Status:** production work in draft PR #3718; no automatic merging or weight-promotion authority. Source `skeleton/ai/game_builder/jeeves_app_runtime.py` is the registered local capability dispatcher.

## Verified app source discovery (branch scan)

The scan enumerated **155 direct entries under `skeleton/`**, **109 under `skeleton/ai/`**, **151 game-builder modules**, **226 crawler/Dragon entries**, **120 Jeeves entries**, **47 AI-forge entries**, **33 additional core-forge entries**, **57 AI training entries**, **54 model-runtime entries**, **24 AI assistant entries**, **74 organism entries**, and **17 AI-learning entries**. Several of these are overlapping or aliases; these counts **are not** a count of working game features. The exact installed atlas is loaded from the app's own package tree, not invented from a marketing list. A bounded recursive family scan pages deeper modules, while refusing symlinks, dotdirs and sensitive filenames.

Scanned application families include:

- **Original game authoring and production:** typed system editor catalog (at least 40), advanced deterministic genre engines, world/scene/character/NPC editors, game project file trees, chapter/cinematic/story director, screen/combat/physics/survival engines, Godot/browser packaging, original asset/legality and release assurance.
- **Forges and producers:** `skeleton/ai/forge` original game forge, dual-rival forge, verified repair loop, `skeleton/forge` universal component blueprint, typed port/wire validation, era/hardware plans, Godot materialization and structured mirror verification.
- **Crawler and companion:** `skeleton/ai/webcrawler` Dragon articles, video, RSS/idle queues, consent-bound collectors, citation and claim provenance, research strategies, source truth gates, adversarial reviewers, original game knowledge distillation and companion animation. Not every source adapter is executable through local Jeeves yet.
- **Jeeves/AI runtime:** `skeleton/jeeves` capabilities, learning/evidence/memory, forecasting and historical modes, game-engine subsystem, assistant chat/attachments/streaming, provider-runtime policy, model-serving/tokenization/weights, agent scheduling and runtime.
- **Training and model improvement:** `skeleton/ai/learning`, `skeleton/ai/training`, model promotion/rollback, candidate/shadow weights, heldout evaluations, source rights, contaminated data rejection, user-approved learning review and model deployment protection.
- **Application infrastructure:** `skeleton/organism`, `hoag`, `creator`, `masterplan`, `automation`, `security`, `vault`, `shells`, `speech`, `video`, `vision`, `audio`, `providers`, `repo_machine`, `network`, `native`, `assets`, `app`, `tools`, `knowledge`, and `release`.

The full module inventory is available live from `app_atlas(family=...)` or bounded `atlas.deep`. Source discovery is **read-only metadata** and never gives Jeeves a Python import/runtime/shell capability.

## Actual executable Jeeves adapters (initial safe vertical slice)

The tool IDs in `ACTION_DEFS` are the **only** paths the new dispatcher can execute. The registry exposes metadata for each, whether it runs a pure simulation, reads a bounded source, plans work, or creates a human-review proposal. Current adapters include live app taxonomy, real editor catalog/field schemas, every editor's typed source and preview, guarded exact-file source proposal creation, workspace/source listing, canonical system assembly, game prompt/router, supervised Jeeves chapter director and chat, existing `ToolFabric` contract introspection and bounded planning, Universal Forge component graph validation with type/port/cycle checking, Dragon companion state-machine rehearsal, crawler worker discovery and evidence-driven improvement candidate planning.

Important boundaries: the `studio_execution_plane.execute_local_tool_plan` **already implements** a separate set of replayable game actions, but this PR intentionally does **not** route arbitrary model actions directly to it; a future explicit adapter must bind a real typed `GameBuildIntent`, operator permit, cost budget, mirror/evaluation evidence and an exact destination/approval policy. Similarly, rendering Godot exports, receiving arbitrary network research, changing actual neural weights, publishing apps, provider-key access and branch merges remain separate protected systems.

**The user-interface integration** adds the Whole-App Capability Cockpit to the same local Game Studio, with live app-family browsing, typed operation selection, JSON argument editing and direct *stage current editor* action. Staging creates a review proposal; it does not approve/commit a file or change weights.

## Admission, performance and security

- Only a locally selected active project may call the dispatcher. A session-scoped same-origin token protects the HTTP endpoints.
- Every request has a registered operation ID with bounded typed arguments; there is no arbitrary `importlib`, `eval`, shell, filesystem root, URL or provider invocation.
- Registered operations return a result plus a content digest and explicit `model_weights_changed: false`. Each file-edit proposal is checked against an exact original source SHA and runs native editor validation. A separate human-confirmed commit is mandatory.
- App metadata walks use an explicit family root, constrained depth, pagination and source extensions; no executable module is loaded as a result of discovery. No private credentials or internal code are returned by the taxonomy. Source content reads are restricted to explicitly reviewed current-project subtrees and size capped.
- Improvement candidates are research/artifact proposals, never self-authorizing promotion. They require heldout benchmarks, adversarial mirror, security and rights, performance budget, rollback replay and operator gate under the separately governed model lifecycle. A model cannot claim improvement by supplying its own positive verdict.
- Keep CPU costs bounded: editor specs are validated by the existing central editor registry; source pages and previews have finite limits; no additional background worker or recurring in-memory graph copies are created.

## Materially incomplete next milestones (no false claims)

1. **Native engine execution:** typed approved adapters to execute the complete game build, engine preview, asset render, packaging and editor composition with genuine replay receipts, not only configuration previews.
2. **Crawler/source control:** consent-authenticated, SSRF-resilient network adapters for articles, videos and RSS ingestion under Dragon's existing queue/rights/truth gates; source provenance must gate any weight contribution.
3. **Learning:** verified shadow → sandbox → approved weight/adapter training → hyperweight deployment through canonical learning and model-serving promotions, frozen holdouts and rollback; never self-modify unchecked code in place.
4. **Every UI director:** explicit adapter for each editor/service the inventory discovers; build generated typed schema bindings and parity tests, excluding secrets/security-administration scopes. This requires integration and tests per subsystem, not granting arbitrary reflection permissions.
5. **Production chat/voice:** connect actual governed model inference to these typed actions, with user-visible approval and plan/response receipts. Chat orchestration alone cannot author a finished game.
6. **End-to-end release:** cinematic generated media QA, adversarial game playtest, rights clearance, platform portability and full installer/release gates.

**Completion reporting must distinguish:** located modules; registered adapters; executable local implementation; tested adapter; user-reviewed source mutation; and final released functionality. A source module named `dragon_video_worker` is not evidence that video crawling actually ran.
