# Original prototype tuning through the recovered GameForge cockpit

## Integration

The complete Galaxy Studio → GameForge recovery already transfers explicit
10-axis cockpit edits to the standard GameForge tensor and source receipt.
Previously, the eight authored mini-games ignored those edits. This patch
adds a deterministic opt-in native tuning compiler that affects actual Godot
game logic without rewriting the existing 10-stage pipeline.

Only explicit slider edits are applied:

| Axis | Native runtime effect | Scope |
| --- | --- | --- |
| Tempo | Player movement speed, bounded 75–125% of original | All eight |
| Risk | Extractor heat per second | Extraction |
| Risk | Checkpoint race time deadline | Racing |
| Risk | Guard detection radius | Stealth |
| Scarcity | Hydration depletion | Survival |
| Lethality | Starting HP | Combat |

The compiler chooses fixed numeric templates and bounded float constants;
the user cannot inject arbitrary GDScript. The remaining axes stay in the
authoritative ten-axis tensor and appear explicitly as unmapped in a
per-mode tuning receipt. The source is never misrepresented as having
implemented every control.

A no-edit run emits exactly the prior three-file prototype and keeps its
existing ledger and project source. With explicit knobs, a new inert
\`data/playable_tuning.json\` lists the original axis edits, actual derived
numeric effects, mapped and unmapped controls. The standard source manifest
and \`playable_prototype\` response both cover this artifact and the emitted
scene/controller/core-loop source with SHA-256 digests.

The existing Galaxy questionnaire, ten-axis cockpit, optional room quest,
and bonus-scene launcher can coexist with this tuning. The 67 historic
genres are still a catalog, not a claim of 67 released game engines.

## Qualification

After implementation and source completion:

\`PYTHONPATH=.:backend python -m pytest -q
skeleton/testing/test_multigenre_playable_slices.py
skeleton/testing/test_historical_gameforge_convergence.py
skeleton/testing/test_native_godot_quest.py\`

\`cd frontend && node --test scripts/skeleton-forge/multigenre-playable.test.cjs
scripts/skeleton-forge/historical-convergence.test.cjs\`

Plus exact-head backend/frontend/static guards. A Godot runtime test must
independently show all eight native completion witnesses and real device
controls. Native unavailability and skipped security jobs are **not passes**.
No merge/release until qualified.


## Independent reconstruction of playable source

The exact-playable receipt is now verified by
\`skeleton.forge.playable_provenance.verify_playable_source\` before the
canonical Godot static and manifest gates. Unlike a self-consistent SHA-256
list, this verifier recreates every scene, controller, mini-game script,
optional launcher and tuning document from the versioned authored
templates and selected bounded axis values. It then checks that every
source file, launch-scene path, file hash and receipt digest exactly
matches. A forged game script with newly calculated checksums is rejected.

The invariant establishes known-source convergence only. It does not
authenticate a repository owner, digitally sign binaries, prove hardware
playability, or make offline saves resistant to local modifications.


## Progression depth and mystery: game-visible mappings

Historical **grind** (Progression depth) now adjusts the actual win
condition of three playable genres: arena waves 2–4, race laps 2–4,
and factory delivery quota 2–6. A mid-slider 0.5 retains the original
3-wave, 3-lap or 4-shipment challenge. The generated GDScript constant
is the runtime authority and the source receipt records the exact
derived target.

Historical **opacity** (Mystery) now controls actual gameplay hints:
the puzzle no longer highlights the next active switch at high opacity,
and stealth can conceal the radius of guard danger zones. The danger
radius itself remains enforced—hiding the hint never disables detection.
The native script receives a fixed typed Boolean; user-provided strings
cannot become GDScript.

These are purposefully small original-prototype effects, not a claim
that social narrative systems or all 67 specialized genres have been
fully implemented. Other unmapped axes are preserved and accounted for
in the same source receipt.
