# Original Physics Studio — Advanced Executable Reference

**Authored:** 2026-10-12 (Europe/Oslo)\
**Change chain:** `feat/game-builder-advanced-physics-world-20261012` stacked on Game Builder PR #3642.\
**Purpose:** Advance an existing authoring-only physics editor into real, deterministic gameplay without a second game-state authority or copyrighted source assets.

## Delivered runtime

The physics family now runs through `run_advanced_session("physics", ...)` with the same source-bound SHA-256 ledger, replay-only portable savegames, authenticated local studio and hybrid assembly as the established advanced gameplay engines.

- **2D/3D integer worlds:** signed seeded chart identity, 100-unit quantized coordinates, three-component velocity vectors, real 3D depth bounds, 2D z-axis rejection, bounded sources, 1–8 authored rigid bodies and up to 24 static fixtures.
- **Real contact mechanics:** gravity, world edges/floor, collision-layer masks, per-body shape extent, fixed-point air/fluid drag and floor friction, material restitution, mass-dependent body impulse transfer, finite impact-fracture thresholds and deterministic rational *swept* fixture collision to block high-speed tunneling through thin static barriers. Dynamic pairs still use bounded discrete overlap correction; continuous pairwise CCD is not claimed.
- **Joints and controlled forces:** two authored cable anchors, physical proximity attachment, max extension, finite tension and cable breakage; source-bounded fan/magnet motors spend actual battery, while applied impulses consume a finite action budget. Body selection spans every supported index 0–7, never nonexistent identities.
- **World interactions:** authored buoyant water plane, material-dependent magnet attraction, destructible nonpayload bodies and explicit failure on breaking the mission cargo. A physics puzzle objective is earned only by actually moving the protected payload into a physically unblocked target and satisfying the velocity and dwell conditions.
- **Two ending modes:** `challenge` produces a genuine terminal completion; `sandbox` records the same earned milestone but remains playable indefinitely. No arbitrary client field or toggle can mint victory.

### Exactly what counts as advanced

The configured physics editor now has **26 typed controls** and a **25-command original reference vocabulary**. The existing five controls are no longer merely prose; they bound gravity, tick rate, body admission, solver iterations and dimension. The 21 additional controls cover speed, forces, battery, drag, restitution, rope/magnet/fan, buoyancy, brake, substeps and physically earned objective gating. All controls are typed and normalized as reviewed source before execution.

This provides **23/43 advanced executable original reference families** on this feature tree; **20/43 remain authoring-only**. This measure does not say 23 retail-grade native engines or that the full game application is 53.5% done. Godot 4 native parity, actual network rollback, audio, console builds and independent commercial certification are explicitly unverified.

## Example source-driven deterministic gameplay

```python
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene
from skeleton.ai.game_builder.advanced_physics_runtime import default_layout
from skeleton.ai.game_builder.system_editors import make_editor_document
from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session, verify_advanced_session

settings = {"goal_radius": 70, "goal_speed": 300}
layout = default_layout(make_editor_document("physics", settings)["settings"], 0)
layout["goal"] = [300, 960, 0]
authored = make_advanced_scene("physics", settings, layout=layout)
session = run_advanced_session("physics", settings, ("push:east",), scene=authored)
assert session["terminal"] and session["state"]["finished"]
assert session["state"]["bodies"][0]["position"][0] > 200
assert verify_advanced_session(session, settings)
```

This fixture is intentionally a small demonstrable physical game, not a certification of emergent real-world physics.

## Proof/validation coverage

`tests/test_game_builder_advanced_physics.py` contains 19 adversarial test methods as published in this feature branch, including 2D/3D authority, signed scenes, actual cargo motion, sandbox continuation, high-speed thin-wall CCD, environmental contacts, finite motors, mask filters, one-body budgets, eight selectable bodies, rope proximity, replay forgeries, portable save continuation and assembly evidence.

`.github/workflows/game-builder-advanced-system-engines.yml` has been expanded to checkout, compile and run this suite on Ubuntu and Windows exact-head PR commits.

**Pending:** externally observed CI outcomes and independent device/Godot verification. PR remains draft; merge after parent #3642 and security/integration gates. An authored source digest is not a proof of game balance, consumer safety or hardware compatibility.

## Append-only implementation history

- **2026-10-12:** `ae418a9` initial fixed-point physics and authored scenes (improved: replaced physics configuration-only family with executable collisions, impulses, resources and cargo objectives).
- **2026-10-12:** canonical runtime, editor, scene, studio and assembly commits (improved: unified origin authority and avoided parallel unsupervised execution).
- **2026-10-12:** `4059737` swept static-fixture collision (improved: high-speed thin-wall contacts no longer silently tunnel).
- **2026-10-12:** `3e1d1e6` body-budget and motor correctness (improved: source can select all eight admitted bodies; motors spend battery only while powered; one-body presets no longer fail default authoring).
- **2026-10-12:** `69e6292` adversarial CCD, bounded-body and selection regressions (improved: true test coverage for edge-case physics mechanics).

### Limits and next substantial vertical

Industrial-grade broadphase, rotations, continuous **dynamic pair** CCD, 3D collision manifolds, proper fluids, SIMD/GPU force fields, ragdoll rigs, full Godot physics parity, hardware characterization and automated competitive quality gates remain unimplemented. The next physically meaningful build should integrate these with authored vehicles and platformers through approved cross-system source contracts rather than just increasing the number of editor options.
