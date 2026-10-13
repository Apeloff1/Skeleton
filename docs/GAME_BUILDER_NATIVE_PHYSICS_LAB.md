# Advanced Native Physics Laboratory

**Authored:** 2026-10-12 (Europe/Oslo)
**Dependency:** Game Builder #3642 → Physics #3661 → Dynamic CCD #3662 → SAT #3664 → Rotational sweep #3665 → Native Physics #3666.

## Capabilities

The original source-bound Python physics game has 40 typed controls. Native Godot 4 has a narrower, actually implemented profile: one original 2D AABB body, a finite fixed step, a zero-powered motor budget, true gravity, signed impulses, airborne movement, floor/wall contact, linear/angular friction and damping, real goal checks, and finite challenge or endless sandbox outcomes.

Native gameplay is independently computed by GDScript from reviewed game.json settings, authored scene source and a bounded action transcript. Source proof.json records the expected Python independently replayed final state; headless native validation compares every projected field and fails on mismatch. The game is not a screenshot or Python-state playback.

Unsupported multi-body collisions, extra fixtures, water interaction, free 3D rotation and original oriented SAT are intentionally rejected at native export. Godot built-in RigidBody equivalence is not claimed.

## Studio and users

Select **Prepare native physics demo**. The local Studio sets the compatible one-body source knobs, requests a signed scene template from its authenticated authoring API, removes the default additional fixture, signs the final source and independently starts its original game session. The ordinary export button is enabled only when this source has the exact native profile and supported action history. No project files are automatically overwritten, and source packaging is not hardware qualification.

Use **Download playable Godot 4 game project**, extract, then run the native game. Headless proof command: `godot --headless --path godot -- --verify-physics`. Native proof output must contain `NATIVE_ADVANCED_PHYSICS_OK`. Keyboard gameplay: arrows/WASD impulse; J/K angular torque; B brake; Space step.

## Evidence

Python tests cover exact editor and scene digests, signed negative-axis impulses and angular braking, original challenge/sandbox behavior, airborne gravity and real floor contact, tamper denial, ZIP hashes, authorized writes, and the Studio's native profile gate. Both Windows 2022 and Ubuntu 24.04 use pinned Godot 4.4.1 actions to execute signed gameplay independently. Ubuntu additionally exports and replays a Linux executable.

The current exact-head GitHub run—not file creation—is the only evidence of cross-platform CI success. PR remains draft until those actual results and parent branch integration are resolved. No production-device, console or rights certification is implied.

## Timestamped improvements (2026-10-12)

- Original independent native gameplay (improved: real GDScript engine rather than data-only templates).
- Signed scene and source custody (improved: no untrusted client data can approve release).
- Signed arithmetic fix (improved: negative momentum and angular damping match the reviewed Python source).
- Airborne gravity implementation (improved: physical falling and floor impacts).
- Studio preset preparation (improved: one-click original authored scene generation without bypassing validation).
- Exact-head Windows/Linux proof gates (improved: runtime parity assertions instead of inspection-only contracts).

**Next native target:** reviewed static-fixture collision, then more complex oriented contacts and multi-body parity; cross-system adapters must remain opt-in and source-reviewed.