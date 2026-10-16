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
