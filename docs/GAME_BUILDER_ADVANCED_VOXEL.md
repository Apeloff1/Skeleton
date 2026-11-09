# Original Voxel Construction — Advanced Reference Milestone

**Date (UTC): 2026-10-12.** Source branch: feat/game-builder-advanced-voxel-20261012, stacked on unmerged #3642.

This milestone replaces a voxel-only settings form with a **source-verified, offline, deterministic 3D-cell sandbox game**. The player mines physical resource blocks, builds supported structures with finite inventories, crafts and installs light sources, explores bounded authored sectors, observes day/night and falling sand, and can earn a nonterminal construction checkpoint. The same original game continues after the checkpoint.

## What is executable

- Exact typed 3D source scene: fixed, nonmineable bedrock and a sorted bounded occupancy grid; source-bound spawn, dimension, material skins and authored block positions; tampered scene checksums fail.
- Advanced game state: player position and orientation, voxel occupancy, finite inventories, stamina, health, visits, torches, day/night light, mined ore, authored construction, sand settling and optional terminal retirement.
- Mandatory causal constraints: occupied space blocks movement, construction needs physical support and inventory, digging needs a removable physical block and stamina, crafting consumes actual mined ore and wood, darkness damages an unlit player, player gravity follows removed support.
- Deterministic event/state hashes for every action. Authoring scenes, CLI gameplay, offline save continuation, verifier, assembly proof and local Studio's generic session controls use the same authoritative runtime.
- Fifteen additional source-validated controls are combined with the five existing typed voxel knobs. The visual UI is still a bounded reference view, **not** a volumetric production editor or commercial 3D renderer.

## Verified scope limits

The fixed-height, maximum 12×12 scene and 2×2 active-sector window represent a deliberately small *reference game*; they do not simulate all 64-size chunks or 512 visible chunks in a modern voxel streaming engine. The configured chunk edge controls the local authored extent (8–12), and the visibility budget limits accessible test sectors (up to four). Large worlds, GPU meshing, greedy mesh/LOD, chunk persistence beyond the source replay, realistic fluid mechanics, collision sweeps, networking, controller/native Godot export and performance certification are **future work**. This branch does not claim any of these.

The 43-family catalog gains a 30th advanced reference gameplay family (29 prior + voxel) **only if exact-head tests succeed**. Native Godot families remain a separate, smaller qualified set; no commercial, hardware or legal certification is implied. Source lineage and review rules are unchanged.

## Usage

    python -m skeleton.ai.game_builder.system_editor_cli scene-template --editor voxel --seed 2
    python -m skeleton.ai.game_builder.system_editor_cli play --editor voxel --seed 2 --actions actions.json
    python -m unittest tests.test_game_builder_advanced_voxel -v

On pull request CI, the Advanced System Engines workflow compiles source, runs the new adversarial tests and reruns existing engine/editor regressions on Ubuntu and Windows.
