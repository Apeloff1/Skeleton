# Walkable original-studio game tranche — 2026-10-30

**Review state:** 20 stacked, draft PRs #4472–#4491, not merged or release-certified. These changes build upon the original 512-project, eight-section source catalog and earlier private producer/export contracts. This document does not claim that local pytest or required CI passed.

## Functional output now authored in source

- A new offline **interactive story** mode uses the real source-authored quest stages, branches, prerequisites and rewards. Buttons and accessible text afford actual browser interaction; source text is inert JSON with script-tag escaping. Replay JSON is re-evaluated by the Python quest engine, not trusted as browser proof.
- A new separate **walkable 2D scene** mode runs a deterministic 18×12 original grid, collision blocking, guaranteed marker reachability, keyboard/WASD and touch controls, proximity-bound source object interactions, and source-authored quest choices. It is an actual 2D playable prototype, not a 3D scene or native genre implementation.
- Offline packaging supports backward-compatible V1 (five files, grid+SVG+WAV), V2 (six files, plus interactive quest) and V3 (seven files, plus walkable.html). Each variant receives a different, strictly validated canonical manifest. Every generated file is content-addressed and reverified after export.
- Operator batch, parallel and source-bound resume workflows support exact selection and variant matching. Independent project workspaces and measured CPU/RAM/disk reserves gate admission. The parallel producer processes resource-admitted waves rather than blindly launching all projects.
- A new read-only host telemetry layer distinguishes measured physical RAM, swap and app-managed disk spill. GPU allocation is refused without independently measured VRAM. Shared GPU+CPU memory must be charged once against the same physical memory; this is **not** automatic GPU paging, virtual-memory reconfiguration or Apple silicon firmware modification.
- A read-only portfolio census enumerates verified, missing and corrupt/wrong-mode outputs across any registered requested portfolio and emits a deterministic chain hash. No file deletion, unearned rights certification or hidden incomplete jobs.

## Explicit owner workflows

Create two existing private directories, and choose a single project or `--all` explicitly:

```bash
mkdir -m 700 .studio-work .studio-output
python -m scripts.studio_ecosystem_production_cli \
  --private-root .studio-work --output-root .studio-output \
  --project studio_arena_fighting_glacial_fjord --walkable-story
```

To generate multiple distinct projects with resource-admitted concurrency:

```bash
python -m scripts.studio_ecosystem_production_cli \
  --private-root .studio-work --output-root .studio-output \
  --parallel --walkable-story \
  --project studio_aerial_traversal_amber_highlands \
  --project studio_puzzle_expedition_copper_mesa
```

Later run the same game selection with `--resume` instead of `--parallel`. Resume reuses only complete, source-current, exact-variant packages; it rejects corrupt or mismatched packages rather than overwriting them. Incomplete outputs require the separate explicit manual quarantine action.

To validate a copied original browser story transcript, run:

```bash
python -m scripts.studio_quest_transcript_cli \
  --project studio_arena_fighting_glacial_fjord \
  --transcript /path/to/choices.json
```

That verifies only authored quest progression and simulator reward state. It never attests real-world evidence.

## Focused qualification sequence

At the **completed final stacked head**, run:

```bash
python -m pytest -q \
  tests/test_studio_ecosystem_story_html.py \
  tests/test_studio_ecosystem_story_review.py \
  tests/test_studio_ecosystem_walkable.py \
  tests/test_studio_ecosystem_offline_bundle.py \
  tests/test_studio_ecosystem_offline_verify.py \
  tests/test_studio_ecosystem_preview_batch.py \
  tests/test_studio_ecosystem_resume_batch.py \
  tests/test_studio_ecosystem_parallel.py \
  tests/test_studio_ecosystem_hardware.py \
  tests/test_studio_ecosystem_production_cli.py \
  tests/test_studio_quest_transcript_cli.py \
  tests/test_studio_ecosystem_census.py \
  tests/test_studio_interactive_full_pipeline.py
python -m compileall -q skeleton/ai/game_builder scripts
```

Then verify exact-head GitHub workflow checks and applicable security/repository/artifact policy checks for every non-draft merge candidate. Draft-skipped jobs, queue states and superseded success cannot certify these branches. No bypass of fail-closed release controls.

Remaining substantive gaps: original full genre mechanics, 3D camera/rendering, multi-actor NPC AI, physics/audio fidelity, on-device GPU/offloading integration, complete multi-ending game content and human-reviewed original rights provenance. The new browser and grid runtimes demonstrate real local authoring functionality, but do **not** close those release obligations.
