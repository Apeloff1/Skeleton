# Native playable multigenre creator expansion — November 13, 2026

## Historical convergence

The full Galaxy Studio catalog already contains 67 game genres and 274
subgenre choices, but the shipped canonical source-backed original-game
mini-loop library previously contained only three executable archetypes:
extraction, combat_loop, and pipeline. Choosing an unfamiliar genre in
the original playable content overlay silently fell back to extraction.

This recovery adds five original **self-contained and playable 2D Godot**
prototype loops: puzzle (ordered switch interactions), racing (checkpoint
time trial), survival (scavenge and manage hydration), stealth (guard
detection and intel extraction), crafting (collect, workshop and deliver).
Each supports manual movement, visual objective markers, a visible player,
a HUD control hint, deterministic headless autopilot, explicit wins/losses
and a bounded frame/time budget. The three existing loops remain present.

## Actual app integration

The existing guided GameForge questionnaire adds the opt-in
**Playable genre prototypes** control. All eight exact backend-supported
choices are displayed with truthful descriptions and accessibility labels.
A user may add the prototype as an auxiliary Godot scene or **explicitly
make it the project's run/main_scene**. The latter option changes the
actual startup project wiring; it does not pretend a hidden scene is the
launched game.

The backend accepts \`playable_content\`, \`playable_archetype\` and
\`playable_main_scene\` only when explicitly opted in. The feature remains
Godot-only and rejects unknown mode IDs and conflicting native quest
startups. The project's canonical source manifest, GDScript static
checker and optional native Godot playtest run after content is attached.
The API reports selected archetype, source scene and actual startup scene.

The original extraction/world/quest main scene continues unchanged
unless a new startup choice is explicitly made. If native quests are
also requested, the standalone mini-game may be included as extra
content but cannot override the existing room-entry quest scene.

## Scope limits

These are true complete small 2D gameplay loops, not polished full
versions of the namesake genres. In particular the 2D racing mode is
a top-down checkpoint time trial, not a physical car simulator; puzzle
is a switch order, not a comprehensive puzzle editor; survival
implements limited hydration and resource collection. All 67 Galaxy
genres remain recognized but 59 do not have a dedicated native
mini-loop in this package. Do not confuse source/static contracts with
successful physical device acceptance.

## Qualification

Focused source and UI tests after completion:
\`python -m pytest -q skeleton/testing/test_multigenre_playable_slices.py
skeleton/testing/test_native_godot_quest.py\`,
\`cd frontend && node --test scripts/skeleton-forge/multigenre-playable.test.cjs
scripts/skeleton-forge/historical-convergence.test.cjs\`.

Native functional verification must boot **each of eight scenes** in
real Godot 4.3 headless mode, check the ARCHETYPE_LOOP_COMPLETE marker
and exit status, then exercise manual keyboard and controller behavior on
real hardware. Windows 11 installer, source mirror, security/malware,
dependency, artifact and source-provenance gates are independent.


## Fully accessible original gameplay

All eight original prototypes now expose a live text HUD showing the
objective and current progression. The existing extraction, combat and
logistics prototypes also render visible loot/enemies/workstations, rather
than headless-only internal state. Player movement accepts normal Godot
ui_* keyboard/controller inputs. On actual touchscreen-enabled systems the
controller installs a visual D-pad and dedicated USE button, with bounded
input pressed/released signals and viewport relayout. Manual combat and
factory interaction now require player input, while headless autopilot
remains an independent executable-test mode.

When a bonus mini-game is attached without selecting it as main,
the generated project includes a PlayableHub autoload with a real
in-game World / Mode switch button. This lets players launch the additional
mode and return to the canonical Godot world without opening the editor.
Changing scenes restarts the current room-world scene; existing saved
quest snapshots remain in the QuestRuntime autoload but are not
automatically replayed into the restarted world.

The additional launcher is never written for non-opt-in builds.
No arbitrary scene path is accepted; only the eight authored registry
values can reach the launcher template. The source manifest and static
checks cover the additional autoload script and revised project.godot.

## Separate native qualification

\`skeleton/testing/test_multigenre_native_godot.py\` exercises each
prototype in a real, installed Godot binary when available. Its witness
must contain an exact matching ARCHETYPE_LOOP_COMPLETE marker and a
zero-exit headless boot. Missing Godot is a **skip, never a pass**.
Touch/keyboard/controller interaction on physical devices remains
independently unverified until tested; static assertions alone do not
prove real device behavior.


## Honesty-first Galaxy genre suggestions

The canonical 67-genre Galaxy catalog can now recommend the nearest
one of eight **actually implemented** prototypes for a deliberately
small set of semantically related genres, for example racing → racing,
tycoon → production pipeline, and extraction shooter → extraction.
The creator never automatically enables a mini-game or changes the
selection; a user must explicitly press "Use this prototype".
Unsupported modes such as RPG and 2D platformer show **no fake playable
recommendation**. The original full design profile always remains
independent of this suggested mini-game and retains its source receipt.
