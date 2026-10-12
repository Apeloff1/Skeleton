# Original Dialogue: Independent Godot 4 Native Milestone

Date: 2026-10-12 (Europe/Oslo). Status: draft until exact-head native CI passes.

## New operational capability

An actual native Godot 4 social game now runs independently authored GDScript
rules. It is not a screenshot viewer, Python snapshot player or LLM proxy.
Players physically move among three source-authored locations, interview
present speakers, pay for support/challenge choices, change trust and
reputation, keep bounded interpersonal memories, corroborate first-hand
statements at an archive, and optionally retire after earning consensus.

Up to eight individual speakers have actual per-person runtime state.
The remainder of configured speaker catalogs (up to 500) are explicitly
unmodeled; no claim is made that they are independently simulated.

## Complete state parity and protections

Reference Python game sessions are independently replay-verified before export.
The native game receives original settings and signed authored scene, and
an expected result for its verifier. Godot then runs its own mechanics and
compares every field of the resultant world state, not a victory flag.
Scope includes speaker identity, trust, patience, memory, original direct
evidence, resources, societal decisions, outcomes and entire source history.

Godot's JSON numerical representation is normalized only for finite integral
numbers. Strings, booleans, fractions and unsafe values cannot silently pass
as forged integer evidence.

The native workflow tests on Ubuntu and Windows with eight original scenarios:
empty, social consensus, epilogue, challenge, physical speaker journeys,
memory decay, bounded sparse speaker cohort and disabled consequence/memory
mode. It also mutates four real Godot proof files to demand native rejection
of fabricated trust, consensus, firsthand evidence and remote interviews.
A Linux executable export must run and independently verify the scenario.

## Existing permissions and custody

The native exporter builds bounded, content-hashed source files. The
existing offline CLI Godot export requires trusted local operator permission
and never overwrites existing paths. The local Studio ZIP endpoint retains
its source-session token and fixed-path archive allowlist; it does not mutate
the user's original game project or enable external calls.

Files:
- skeleton/ai/game_builder/advanced_dialogue_godot.py
- tests/test_game_builder_advanced_dialogue_godot.py
- .github/workflows/game-builder-advanced-dialogue-native.yml
- existing native exporter, CLI, Studio HTTP and visual Studio integrations

## Timestamped change history

- 2026-10-12 — original independent Godot simulation (real native social play).
- 2026-10-12 — complete speaker/evidence/memory replay comparison (no victory-bit-only proof).
- 2026-10-12 — explicit local CLI and token-protected Studio ZIP access.
- 2026-10-12 — eight cross-platform scenarios and four native evidence attacks.
- 2026-10-12 — exported Linux desktop binary execution gate.

## Remaining release requirements

Actual source CI must be green on the exact head. Native hardware
certification, console SDK porting, publication rights, commercial release
and AI weight improvement remain unverified. This source PR is stacked on
draft Dialogue PR #3677, which depends on previous causal, Economy and Game
Studio branches. None is represented as already merged into main.
