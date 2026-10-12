# Independent native Godot 4 source-fixture collision custody
**Authored:** 2026-10-12, Europe/Oslo. Stacked on original physics/source SAT contact custody #3682.

## What changed in real executable gameplay
The existing independently executing original Godot 4 physics laboratory previously proved the final fixed-point state and aggregate collision count. That could not distinguish a physically correct result from an implementation that accidentally collided with the wrong source fixture while ending at the same position.

The native interpreter now constructs a source fixture-count vector on reset, increments the **exact authored fixture index when its actual Minkowski swept or penetration collision resolves**, and maintains the same bounded 96-entry ordered history as the reviewed Python AABB physics reference. Every entry includes the source fixture index, original physical body ID, contact kind, physics tick/frame and actual collision position. Neither world-edge collisions nor non-solid authored layers may create a source fixture record.

The Python export now includes the complete per-fixture vector and bounded event list in its independently replayed proof. The native Godot `--verify-physics` execution compares these additional attributes field-by-field, alongside the existing validated physics coordinates, velocity, impulses, angular motion, finite battery/health and challenge/sandbox outcomes. Incorrect collider identity, event order or contact count now fails the native source proof even if the cargo ends in the correct place.

## User and developer experience
The change is part of the normal original native Godot package and works with the physically authored platformer, racing and sandbox obstacle encounters already exported by the game Studio. Existing native gameplay remains an interactive fixed-point one-body 2D AABB reference, not a complete native copy of all original genre-specific progress, quests or editor systems.

## Exact-head validation
- Four new Python regression cases verify nontrivial source collider receipts in the packaged proof, ignored collision layers, original fixtures absent and forged native-source collision metadata rejection.
- The existing pinned Godot 4.4.1 Windows/Ubuntu CI runs ten independently authored source game/replay scenarios, including static fixture impact, masked avoidance, authored platformer/racing/world obstacle variants and an exported Linux native executable.
- A committed change is **not** proof of cross-platform native equivalence: only final exact-head Godot process results on both targets authorize marking this milestone validated.

## Honest remaining limits
Source custody parity is implemented for the previously verified one-body 2D AABB native profile. The Python reference also produces exact source IDs for discrete oriented SAT and temporally swept rotation; **native Godot does not yet independently implement/verify those rotational geometries**, and this milestone does not claim it does. High-frequency contact evidence retains the last 96 records with complete per-fixture counts; full ordering after 96 emitted records cannot be reconstructed and dependent NPC systems fail closed.

## 2026-10-12 improvement chronology
- Advanced Physics canonical source objects (improved: collisions with actual original fixtures).
- Source-indexed Python AABB custody (improved: original fixture identities survive replay).
- Original multi-incident eyewitness campaigns (improved: events attach to actual collided source objects).
- Oriented and rotating SAT custody (improved: physically rotated contacts identify source objects in Python).
- **Native physical source identity parity** (improved: independent Godot execution verifies actual authored fixture IDs, not just resulting position).