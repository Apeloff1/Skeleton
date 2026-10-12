# Cross-engine Physics Handoff — Original Game Motion to Training Exercises

**Authored 12 October 2026 (Europe/Oslo)**. Source stack: Game Builder #3642 → Physics #3661 → translational CCD #3662 → SAT #3664 → rotating sweep #3665 → native Godot subset #3666 → this cross-genre interoperability milestone.

## Implemented

Four established playable original game engines — **platformer, racing, flight and sailing** — can now feed independently re-executed physics exercises. This is not configuration-only catalog growth.

1. The originating gameplay receipt is replayed with its exact reviewed editor settings and signed scene to reconstruct ground truth. Client-supplied final health, position, currency, weather or victory cannot be substituted.
2. The reviewed adapter derives a new source-owned physics level from the game session's actual last position, velocity, altitude/lane, bank/heading, mass and material; signed hazards/corners/ridges/shoals become real authored static collision obstacles. Input ranges, object counts, collision layers and active goal are bounded. No original game's state or rules are overwritten by the exercise.
3. The derived scene is validated and signed by the canonical scene authoring layer. Real physics actions run through the previously tested SAT/CCD reference engine, and the resulting state and trace are independently replay-verified. Physics coefficient variation can be requested only through a small typed, explicit allowlist.
4. The new evidence record contains both reconstructed game sessions, exact origin and derived scene digests, authorized action receipts, source motion fingerprint and explicit flags for no native parity or weight promotion. A second verifier regenerates the entire process and rejects any forged field.
5. The authenticated loopback studio now exposes **Practice game physics from this scenario** only for the four supported source families, displaying physics state, obstacle mapping and provenance without changing or deploying the original game. No external link, crawl or autonomous training promotion is added by this lane.
6. **14 adversarial tests**, including all four engine families, signed authored layouts, actual physics coefficient responses, source/receipt tampering, setting/command boundaries, trained-weight promotion denial, original-game immutability, user-visible UI/endpoint presence, and actual authenticated HTTP success/denial tests. Windows and Ubuntu exact-head game-engine CI include the full new implementation and suite.

## Native physics / engine separation

The parent milestone #3666 builds independently playable Godot physics games with a restricted, proof-checked single-body 2D profile. That native profile has separately **passed Windows and Ubuntu** headless replay gates; this new bridge does *not* falsely claim Godot parity for all of the signed, extended SAT/cross-engine physics exercises.

The platformer, racing, flight and sailing engines remain the authoritative owners of their existing worlds, collision and score semantics. Derived physics levels are **sidecar exercises for mechanics comparison and safe learning**, not a live replacement of those genre engines. This is deliberate: quietly changing genre rules on export would invalidate signed gameplay and multiplayer/save determinism.

## Current limits

Cross-genre mappings use bounded normalized motion, not dimensional real-world aerospace/marine units. Obstacle locations are newly authored source-derived hazards, not proven one-to-one geometry with original assets. A signed exercise is not by itself a promoted AI weight; training still requires future independent evaluation, competitive quality gain, review and approval. Native Godot contact/ragdoll/device parity, cross-domain continuous live solver and standalone Windows installer remain separate milestones.

## Next release controls

- Exact-head Ubuntu/Windows full game builder and focused cross-game adapter tests.
- Separate PR dependency reconciliation back to the main Game Builder.
- Independent physical/visual playtest, calibrated unit mapping, deterministic full cross-system replay and device-budget benchmarking before calling the sidecar a native production physics common kernel.
