# Game Studio Expedition — Seven More Executed Systems

Implementation scope: \`Apeloff1/Skeleton\` PR #4192, October 20, 2026.

## Milestone 1: Source-bound controller calibration and remapping

\`game_frontier_expedition_input.py\` implements source-preserving button
remaps, analog axis calibration (deadzone, engage/release hysteresis,
inversion), frame-ordered device observations, deterministic combined
digital/analog action receipts and an independent replay verifier.
Physical controller input is not claimed until collected by a host HID/engine.

## Milestone 2: Canonical multi-quest, multi-ending runtime

\`game_frontier_expedition_quests.py\` defines typed quest stages,
per-objective prerequisites, replayable progression and three distinct
original endings. Quest flags cannot be laundered into game physics.
The Godot scene reads world-bound \`quests.json\`, advances authored stages
on real travel or story choices and records its chosen ending on victory.
The native script is intentionally governed by the same source as its
independent Python replay; an external human creative review is still
needed for quality and legal signoff.

## Milestone 3: Original generated PCM soundtracks

\`game_frontier_expedition_audio.py\` renders actual 16-bit mono RIFF/WAV
from bounded homebrew notes and synthesized weather/biome soundscapes,
with oscillator timbres and per-source checksums. The integrated compiler
packs PCM bytes into an exact-world JSON base64 resource. Godot creates
an \`AudioStreamWAV\` and \`AudioStreamPlayer\` to play the generated audio.
Playback must be qualified by the pinned Godot engine check; native acoustic
quality, hardware DAC output and musical originality review are not implied.

## Milestone 4: Animated source-bound cinematics

\`game_frontier_expedition_cinematics.py\` compiles original opening,
threshold and arrival shots with fully interpolated camera keys, dialogue,
GDD source identities and hash-linked frame receipts. It exports a playable
Godot Camera3D scene. The main Godot expedition loads the optional scene
and activates a clip when the player arrives at a canonical location.
The authored frame journal is not footage from a rendered native process.

## Milestone 5: Geometry-aware LOD scheduling

\`game_frontier_expedition_render.py\` chooses actual authored mesh LOD
from camera XYZ, visibility range, triangle budget, object count, update
cap and hysteresis; it journals every frame's geometry selection.
The native Godot scene now periodically evaluates LOD mesh choices
where source resources are present, using visible geometry fallback
when optional mesh import is unavailable. FPS is not fabricated.

## Milestone 6: Dragon's independent adversarial review

\`game_frontier_expedition_dragon_review.py\` challenges Dragon's four
objective-route readings across up to ten original games. It re-executes
real game actions, checks route and event state, and attempts six
independent attack mutations: metrics inflation, false learning promotions,
native-origin laundering, falsified damage, broken receipts and copyright
clearance misclaims. Only scoped learning notes can be admitted, never
unreviewed model weight promotions.

## Milestone 7: Crash-before-write / after-write fault recovery

\`game_frontier_expedition_crash.py\` drives real source-bound SQLite
gameplay through deterministic fault injection, including crashes before
commit and after commit but before host acknowledgement. It reopens stores,
replays actual action receipts, and reconciles lost acknowledgements
without duplicating progression. This is a *simulated crash test*:
neither actual kernel/process failures nor multimonth uptime is certified.

## Unified build and evidence

\`compile_original_campaign()\` now exports quests, cinematics, generated
PCM audio, render LOD frame journals, Dragon adversarial proof, crash-test
policy, controllers, canon dialogue, world data, original OBJ geometry,
Godot game scene/GDScript, QA and blocked release signoff together.
The source-bound manifest records digests for every component.
\`verify_original_campaign()\` redoes the build independently and
compares exact artifact bytes.

Backend Quality and focused Game Frontier validation compile and exercise
the new modules. Native Godot Smoke runs a complete original winning
route on its pinned binary and checks the sound/quest resource integration.
Any failed check blocks merge. No original 100-volume masterplan task is
treated as complete solely from implementation or simulated evidence.
