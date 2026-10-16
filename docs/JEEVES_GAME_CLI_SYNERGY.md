# Jeeves × Game Creator CLI: unified developer workbench

The existing Skeleton developer CLI now exposes a read-only Jeeves game workbench. It uses the same game workspace, canonical era compiler, existing Jeeves BuilderBrain, source verification, asset inventory and Godot binary discovery as GameForge. It does not fork an AI engine, add a provider SDK, assume model checkpoints or silently change code.

## Commands

    python -m skeleton dev game init original-rpg --vision "An original fantasy RPG"
    python -m skeleton dev game jeeves plan --project ./original-rpg
    python -m skeleton dev game jeeves context --project ./original-rpg
    python -m skeleton dev game jeeves next --project ./original-rpg
    python -m skeleton dev game build --project ./original-rpg
    python -m skeleton dev game jeeves audit --project ./original-rpg
    python -m skeleton dev game jeeves handoff --project ./original-rpg

## Operations

- plan: deterministic local Jeeves BuilderBrain plan, seed and hash. Explicitly reports model_inference=false and checkpoint_verified=false.
- context: bounded UTF-8 design notes and SHA-256 identities; no authored continuity claims.
- audit: canonical Forge source checks, asset inventory, binary discovery and explicit unverified release/playthrough rows.
- next: prioritized concrete developer commands grounded in the actual failed checks.
- handoff: JSON summary of plan, recommendations, source identity, design-note hashes and outstanding checks.

No model inference is promised by these deterministic commands. They form a usable handoff to the existing Jeeves/model integration, not a second credential-bearing runtime.

## Authority and safety

Workspace schema and era are validated before planning. The source auditor delegates to the existing generated-source verifier. Design context is bounded to 128 regular UTF-8 md, txt or json files, each no larger than 256 KiB; symlinks are rejected. All Jeeves operations are read-only. The existing GameForge build command remains the selected mutating operation.

Godot binary discovery is not a playthrough pass. The headless_playthrough and release_export checks remain explicitly unverified. production_qualified stays false. A handoff hashes design notes instead of silently changing or inventing canon.

## Unfinished extensions

Future qualified integration should connect optional in-process inference through the canonical provider runtime, typed edit proposals and approval, per-scene continuity, simulation-driven repairs, checkpoint-backed assessment, and rollback. These require real operator authorization and run evidence.

Focused coverage: skeleton/testing/test_jeeves_game_cli.py. Existing architecture checks remain mandatory.


## Model-backed authoring: opt-in proposals

The propose action is the only model-inference operation in this workbench
pass. It uses the existing canonical provider registry and governance
admission; a missing model or rejected request fails closed, without an
imitation template fallback.

    python -m skeleton dev game jeeves propose --project ./original-rpg --kind quest --brief "An original political quest with branching outcomes"
    python -m skeleton dev game jeeves queue --project ./original-rpg
    python -m skeleton dev game jeeves review --project ./original-rpg --digest YOUR_SHA256
    python -m skeleton dev game jeeves apply --project ./original-rpg --digest YOUR_SHA256 --approve YOUR_SHA256

Available game design kinds: character, dialogue, quest, world, mechanic,
scene, animation, cutscene, asset and music. These are TEXT specifications;
asset and music operations do not generate media or edit production game data.

Model outputs must contain exactly six validated JSON fields, with bounded
lengths and safe slugs. Invalid JSON, duplicate fields, unsupported kinds,
oversized responses or unsafe filenames are rejected. Only explicit
proposals are saved, in private local scratch .jeeves/proposals. New
workspaces include .jeeves/ in the Git ignore list; older workspaces
should add this rule too.

Normally only the game name, vision, era, archetype and explicitly typed
brief are sent to the selected configured model. The optional
--include-notes flag allows sending bounded design-note excerpts.
Referenced design-note SHA-256 identities and the project configuration
identity are bound to the proposal. Context drift while generating, at
review or before acceptance blocks stale proposals.

Review verifies the complete proposal identity and shows the proposed
draft target. Apply requires the matching proposal SHA-256 twice and can
only create a NEW Markdown design draft under design/KIND/SLUG.md.
Existing human-authored work is never overwritten. This is not an
authorization for release, model-weight promotion, game build mutation,
execution, or high-impact changes. Those remain governed by their canonical
creator work-lease and approval boundaries.

Queue lists up to 128 pending receipts and rejects any malformed entry.
The status of a proposal or new design draft is not a model-quality,
continuity, gameplay or production-qualification verdict.

Focused tests:

    python -m pytest skeleton/testing/test_jeeves_game_authoring.py skeleton/testing/test_jeeves_game_cli.py skeleton/testing/test_game_creator_cli.py -q

Unit tests mock network inference. Real model inference, qualified source
builds and full playthroughs require independently observed live evidence.
