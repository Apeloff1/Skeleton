# Historical game-builder convergence ledger — 2026-11-13

All historical work is considered eligible for recovery; however, old Git
compare results alone cannot prove a feature is missing. Archived branches
are substantially behind modern main and may report a file as newly added
even when its identical blob is already on main. Never wholesale overwrite
a modern subsystem without verifying exact content and security contracts.

## Active source-preserving implementation branches

- PR #5296: historic questionnaire, runtime ten-axis instrument tuning,
  36 canonical GameForge genres, all 67 Galaxy specialization choices,
  and cross-navigation to the original deep 14-matrix Galaxy questionnaire.
- PR #5299: archived #807 seven-stage conductor, B038 provenance receipts
  and B039 bounded self-repair, including finite cost/time defenses.
- PR #5302: B023 sandboxed ECS scripts, B024 remappable semantic
  keyboard/gamepad/mouse/touch controls, 67 Galaxy genre control profiles.
- PR #5304: B028 quest-objective runtime, B030 immutable mechanic-pack
  composition, B037 constrained quest synthesis and executable proof bridge.

All are review branches; source existence does not imply these modules
have been merged, installed, or natively playtested.

## Exact-byte-equal archived files already on main

- Project bundle project_save.py and manifest.py
- Quest quest_objectives.py and quest_progress_save.py
- Authored dialogue dialogue_session.py
- Natural-language repair skeleton/forge/creator/nl_repair.py
- Scene safety scene_bytes.py, deterministic input_collision.py,
  and grid_input_adapter.py
- Adventure, design bible, and production planning Jeeves extensions
- Frontier navigation gps.py and Expo location FrontierLocationProvider.tsx
- Frontier worldsim/navigation.py and worldsim/streaming.py
- Game frontier event authority and frontend frontierMinimap.ts

These results cover archive/pre-rebase-mb-project-bundle,
archive/pre-rebase-mb-quest-system,
archive/pre-rebase-choice-ledger,
archive/pre-rebase-gf-b020-char,
archive/pre-rebase-scene-byte-boundary,
archive/pre-rebase-input-collision,
archive/pre-rebase-studio-b-grid-input-adapter,
archive/pre-rebase-adventure-systems-depth,
archive/pre-rebase-design-bible-asset-depth,
archive/pre-rebase-production-planning-depth,
archive/pre-rebase-gf-h-nav,
archive/pre-rebase-gf-j-location,
archive/pre-rebase-807-world-backend,
archive/pre-rebase-mb-gfa,
and archive/pre-rebase-gf-f-char.
The archived branch filenames include date and SHA suffixes in GitHub.

## Modern-divergent historical files; do not clobber

- skeleton/ai/game_builder/project_bundle/bundle_io.py
- skeleton/game/flgb_editor_runtime.py
- skeleton/jeeves/worlds/world_canon.py

Each has a different main blob from its archived version. Review on
behavior and individual safety contracts, not commit count.

## Confirmed rich historic Galaxy Studio sources on main

- QuestionnaireMatrices.tsx: 14 production matrices
- MatrixSliders.tsx and NarrativePhaseSliders.tsx: phase-specific dials
- extraParams.ts: 100 additional customization parameters
- styleSliders.ts: nine semantic visual/audio/director choices
- fallbackGenres.ts: 67 game genres, 274 subgenre entries
- ProductionStudioPanel.tsx, gameEras.ts, presets.ts and /galaxy

The smaller GameForge questionnaire previously exposed 16 broad choices;
the recovery branch expands to all 36 backend votes plus a searchable
specialization selector based on the 67 original Galaxy options.

## Next technical boundaries

1. An authorized versioned per-project design draft with actual handoff
   for all 14 matrices, 100 extras, narrative and style choices.
2. Durable authenticated project cockpit, rather than a new Cockpit()
   for each HTTP command.
3. Connect genre control profiles, sandbox scripts and verified quests
   to the current production/gameplay and native Godot export pipelines.
4. Test true playable behavior, replay/save/load, Windows/local-device
   and hardware resource pressure, not just static templates or JSON.
5. Reconcile remaining branch backlog after exact blob-diff checks.

Never treat pending, cancelled or skipped exact-head CI as success.
No native release/first-install qualification has been established here.
