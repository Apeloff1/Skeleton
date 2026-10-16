# Jeeves standalone game-studio continuation and faithful upscaling

This feature is an incremental capability inside the canonical Skeleton
GameForge/Jeeves developer CLI. It does NOT constitute every-console native
rendering, trained neural weights, completed games, or independently
quality-certified assets.

## Core rule: no arbitrary end to a game project

A finished game needs substantially more than a bootable sample. The
production checkpoint contains 18 *immutable* completion disciplines:
world_and_lore, characters_and_npcs, story_continuity, quests_and_dialogue,
scenes_and_level_design, gameplay_and_mechanics, original_assets,
animations_and_vfx, cinematics_and_camera, music_and_ambience,
user_interface, localization, accessibility, market_quality, source_integrity,
runtime_boot, full_playthrough, performance_and_release.

The original quality requirements cannot be lowered on retry: the design
rubric floor is 90/100 on every dimension, the critic benchmark minimum is
85/100, both sales and critical ratings require top-quartile rank in a
like-for-like period/console/genre cohort, and every discipline must be
independently qualified before finished-game status can ever become true.

These are *acceptance criteria*, not statements that comparators, legal
sources, independent art reviewers, game platforms or hardware test labs
are presently installed.

No total attempt cap, lifetime session-step limit or project deadline is
stored in the policy. The journal is append-only, with no code that ages
out or deletes previous attempts. Each event is an individual, numbered,
create-only JSON record, linked by SHA-256 to its predecessor and the
immutable policy. It retains even identical repeated scrutiny passes,
marking them **not novel** rather than deleting them or falsely calling
them additional independent evidence.

The physical disk, operating system, provider terms, storage quotas and
actual elapsed time necessarily remain finite. **One invocation** has an
explicit bounded scope (1-8 scrutiny passes, bounded render/codec input,
model-resource admission), after which the job is resumable. This permits
indefinite total effort without unkillable inner loops, unavailable
cancellation, infinite budget overruns or GPU deadlocks. Do not interpret
"indefinite" as infinite free compute or permanent retention guarantees
outside the local filesystem.

## Commands: start, inspect, repair/retry, review training evidence

    python -m skeleton dev game init original-adventure --vision "Original complete adventure"
    python -m skeleton dev game jeeves production-init --project ./original-adventure --target nes --genre Platformer --period 1985-1989
    python -m skeleton dev game jeeves production-status --project ./original-adventure
    python -m skeleton dev game jeeves production-cycle --project ./original-adventure --passes 8
    python -m skeleton dev game jeeves production-cycle --project ./original-adventure --passes 8 --repair-generated
    python -m skeleton dev game jeeves production-status --project ./original-adventure
    python -m skeleton dev game jeeves production-training --project ./original-adventure --page 0 --page-size 64

production-cycle evaluates true currently connected checkers for source
integrity, available market evidence, and an actual bounded Godot headless
boot. Unlike a fixed-total-step demonstration, another cycle can follow any
number of earlier cycles without changing the quality floor. The existing
GameForge build repair can be selected explicitly with
--repair-generated. It may overwrite the project-owned generated
build/godot output via the existing GameForge repair loop; it does not
automatically rewrite human design drafts, steal third-party art or promote
model checkpoints. The original gate is re-evaluated after repair.

Missing independent evaluators remain BLOCKED, not passed. Every relevant
gate report explains missing evidence and what cannot yet be claimed. A
passing headless boot does not certify a complete gameplay walkthrough,
and locally supplied sales claims do not establish authenticated publisher
statistics. Other disciplines need real scene/quest validation, simulation,
production rendering, GPU/hardware measurement, reviews and release evidence.

The final project_complete predicate uses the required quality owners for
every gate. In the current patch, many of those domain validators are not
implemented: therefore a real fully qualified game cannot yet be certified
by this workbench. That is a deliberate, surfaced gap, not an automatic
completion flag or quota-driven downgrade.

## Game studio training integration

The append-only ledger is the source of observed fail/pass transitions.
production-training streams them as paginated candidate records with
before/after evidence hashes and actual checker reasons. Candidates are
limited to actual technical checks; self-reported artwork ratings do not
become authorized training examples.

A transition proves only that a checker failed and later passed with changed
input evidence. It **does not prove causal model learning**. Neither a
candidate example nor a quality gate edits local weights, trains a
production transformer or promotes a model. Actual checkpoint training,
held-out benchmarks, regression gates and governance are separate owners,
and no training data may be copied from unauthorized commercial games.
Previous observations are never deleted by pagination. No checkpoint access
is invented when none is configured.

## Historical fidelity, upscaling and new hardware

The authoritative target registry is
skeleton/jeeves/game_console_catalog.py; historical reference engine
profiles are in skeleton/jeeves/game_engine_lab.py. They are checked by
console ID, not guessed by decade or swapped for an unregistered platform.

A source-faithful high-resolution workflow follows six separate decisions:

1. Identify the exact console and era, game style, hardware display geometry,
   palette, tile limits, texture/geometry precision, aspect ratio and frame
   cadence. Never assume 1:1 square pixels on every CRT-era console.
2. Preserve the original internal game/sprite authored resolution and
   silhouette. Source fidelity is not merely a high-resolution image size.
3. Choose integer nearest-neighbor blocks for pixel-faithful presentation,
   or deterministic Scale2x/EPX reconstruction for original palette colors
   and edge-aware pixel placement. EPX does not create new colors or neural
   details; not every historical art style should use it.
4. Preserve display aspect with integer-scaled pixel-aspect ratios and
   explicit letterbox/pillarbox borders. A widescreen monitor should not
   indiscriminately stretch an old 4:3 picture. Higher resolution may
   reveal more original detail only when the source actually contains it.
5. Consider optional display-specific post-processing such as CRT scanlines,
   mask, glow, composite behavior or original low-color/LCD persistence.
   Those are not implemented by the simple PNG upscaler and must be
   qualified by visual comparison; use the project's own shader pipeline
   when available.
6. Only after the source-faithful image passes objective checks, require
   independent art reviews, camera/motion/temporal coherence, controller
   feel, audio playback, accessibility and actual native-hardware or
   qualified emulator timing. Do not claim that an image rescale is
   a complete console renderer or an upgraded 3D world.

The following commands perform real bounded work:

    python -m skeleton dev game jeeves fidelity-plan --project . --target nes
    python -m skeleton dev game jeeves fidelity-matrix --project .
    python -m skeleton dev game jeeves display-plan --project . --target nes --native-width 256 --native-height 240 --screen-width 1920 --screen-height 1080
    python -m skeleton dev game jeeves upscale --project . --target nes --source assets/hero.png --output assets/hero-scale2x.png --mode scale2x --factor 2
    python -m skeleton dev game jeeves upscale-verify --project . --target nes --source assets/hero.png --output assets/hero-scale2x.png --mode scale2x --factor 2 --passes 8

The renderer:
- Uses the existing canonical console PNG decoder/encoder with its 1M pixel
  bound; no unannounced fallback, no overwrites, input/output SHA-256, and
  no source data mutation.
- Implements exact nearest-neighbor factor 1-8 and two-pass edge-aware
  Scale2x at factors 2 or 4. No colors not already in the original source.
- Verifies exact deterministic pixel reconstruction on every scrutiny pass
  with repeated source/candidate hash checks. Repeated deterministic passes
  are not independent expert quality evaluations or GPU measurements.
- The display planner handles rational source pixel aspect, integer
  physical blocks and letterboxing; it emits geometry **plans**, not
  HD texture bytes. If the rendered viewport would exceed the bounded
  PNG codec, it clearly calls for a tiled or GPU renderer.
- The fidelity-matrix inspects *all* currently declared canonical
  reference/native/emulator targets, and explicitly flags native export,
  originality, independent historical image comparison and frame timing
  as UNQUALIFIED. An emulator can support foreign ROMs but still lack
  original source compile/export and an authenticated game playthrough.

Engineering scope: building genuine full native 3D rendering, high
resolution texture authoring, material conversion, modern GPU pipelines,
console SDK export, physics/frame-rate compatibility and every per-era
editor remains **unfinished**. These prerequisites cannot be replaced with
a generic resized PNG and a "100%" UI claim.

Relevant external engineering context:
- Libretro integer/pixel-grid-aware scaling and variable-resolution shaders:
  https://docs.libretro.com/development/shader/slang-shaders/
- Libretro CRT rendering discussion:
  https://docs.libretro.com/shader/crt/
- Godot project aspect and integer stretching:
  https://docs.godotengine.org/en/4.3/tutorials/rendering/multiple_resolutions.html

## Trust and long-term operational behavior

- Existing CLI is the transport, not a second AI service, renderer owner,
  state provider or privileged game execution plane.
- Existing canonical GameForge and Godot playtest produce source/boot
  receipts; Jeeves still uses canonical provider_runtime for model
  inference. Model calls are only explicit and governed.
- Existing official game studio engines, emulation owners and approval
  boundaries remain authoritative; this ledger does not bypass copyright
  review, producer approvals, credentials or protected release gates.
- Every mutable generated output must have a source identity and operator
  control. Failed repairs stay failed; no quality-score inflation.
- Ledger files are small, individually atomic and validated on read; each
  attempted scrutiny pass is retained. If disk fills or a concurrent writer
  collides, the command fails visibly without discarding earlier receipts.
- No fabricated runtime time or review count; event timestamps are
  bookkeeping, not proof of engine or model speed. External asset/media
  copyright and privacy restrictions continue to apply.

## Required verification and acceptance backlog

    python -m pytest skeleton/testing/test_jeeves_game_completion.py -q
    python -m pytest skeleton/testing/test_jeeves_game_quality.py skeleton/testing/test_jeeves_game_authoring.py -q
    python scripts/check_architecture_map.py
    python scripts/check_ai_app_construction.py
    python scripts/check_capability_interfaces.py
    python scripts/check_provider_bootstrap.py
    python scripts/check_enterprise_ai_superiority.py --json
    python scripts/check_enterprise_ai_implementation_notes.py --json

Important remaining milestones: real multi-era scene graph editor coverage,
runtime/asset generation beyond reference previews, era-native renderer
implementation, controller and full game-path simulations, long-horizon
project task execution, independent market evidence verification, model
checkpoint training with held-out gains, continuity proofs and customer-level
release acceptance. The present code proves only the explicit capabilities
above until tests and run evidence are observed.


## Actual bounded 3D frame rendering milestone

The existing historical reference rasterizer in
skeleton/jeeves/game_engine_rendering.py can be driven through a declared
original 3D source document. This is **real pixel rendering** with
perspective, clipping, depth/coverage and typed triangle materials, not a
drawn mockup or future-only plan.

Create design/scene3d.json with the following original scene:

    {
      "schema":"skeleton.game.reference_scene.v1",
      "width":160, "height":120,
      "near":0.1, "far":100.0, "fov_y_deg":70,
      "triangles":[{
        "object_id":"original-player",
        "material":7,
        "shader":"fixed",
        "shader_phase":0,
        "vertices":[[-0.8,-0.7,2.0],[0.8,-0.7,2.0],[0.0,0.9,2.0]]
      }]
    }

Then run:

    python -m skeleton dev game jeeves render-reference --project . --target ps1 --source design/scene3d.json --output assets/frame.png
    python -m skeleton dev game jeeves upscale --project . --target ps1 --source assets/frame.png --output assets/frame-2x.png --mode nearest --factor 2
    python -m skeleton dev game jeeves upscale-verify --project . --target ps1 --source assets/frame.png --output assets/frame-2x.png --mode nearest --factor 2 --passes 8

The selected registered target chooses its canonical historical 3D
renderer:
- early-3D DOS PC: painter-order software raster;
- PS1/N64/Saturn-style fixed-function reference: z-tested Lambert-style
  material lighting;
- PS2/Xbox/GameCube-style shader-era reference: programmable tint/fog path.

The renderer refuses unsupported modern GPU/hardware console targets
rather than emulating them through the wrong renderer. A source scene may
contain 1..4096 bounded typed triangles and up to the reference rasterizer
limit of 320x240 pixels. It does not parse proprietary game data or create
native console binaries. Materials are deterministic synthetic colors, not
commercial assets or full texture/mipmap support.

A successful render has a real frame/color digest, actual covered pixels,
and an immutable PNG source artifact. The reference frame is still NOT a
reproduction of a genuine PS1 GPU, modern-console raytracing, the intended
creative art quality, hardware performance, or a full playable game.
The modern engine render graph in
skeleton/jeeves/game_engine_render_graph.py provides dependency evidence,
not arbitrary-screen-resolution GPU pixels.

Source and output stay inside the original project and are never
overwritten implicitly. The converter's output can pass algorithmic
upscale checks, but still needs professional art review, game integration,
controller experience, cinematography and authentic end-to-end gameplay.

Test: python -m pytest skeleton/testing/test_jeeves_game_render.py -q
