# Game Builder — Rotational SAT Sweep, Spatial Broadphase and Resting Bodies

**Date authored:** 2026-10-12, Europe/Oslo.  
**Source stack:** Game Builder #3642 → Physics #3661 → Translational/Angular CCD #3662 → Oriented SAT #3664 → this milestone.  
**Quality floor:** advanced deterministic source-bound gameplay reference. This is not native engine parity, industrial rigid-body certification, or full continuous convex collision.

## Real executable additions

**1. Discrete rotation-aware swept contacts.** The new `advanced_physics_rotational_sweep.py` samples intermediate poses between two trusted canonical frame states for source-authorized rectangular bodies and signed static fixtures. For each candidate, the SAT narrow phase checks the actual interpolated center and millidegree orientation, in stable authored order, including true Z-depth separation for extruded 3D geometry. An impact rolls the pair or body back to the last non-overlapping pose and transfers bounded momentum, material-constrained restitution and existing finite spin/impact-fracture response.

**2. Spatially indexed candidate discovery.** Original body swept envelopes are expanded by the full oriented circumscribed radius, covering *every intermediate orientation*. Deterministic integer 2D/3D spatial cells deduplicate source-order dynamic pairs and conservatively filter static-fixture candidates. The broadphase does not trust client-provided object IDs, positions, masks or lengths; admission depends on validated original scenes and canonical gameplay state. Counters report actual candidate pairs, fixtures, skipped pairs and SAT probe work.

**3. Bounded computation.** Six additional typed controls bring Physics to **40**: rotational sweep enablement, maximum SAT samples (8–128), spatial cell size (80–640 quantized units), resting linear threshold, resting angular threshold and required consecutive support frames. The samples and cell grids are finite; no unbounded recursive approximation or external physics kernel is loaded. The source-signed default has a 96-sample ceiling, not a promise of exact analytic TOI.

**4. Rest and wake correctness.** A reference body can settle only after repeated low-energy frames against a real authored world floor or original horizontal static support. Source-authorized impulses, torque, powered motors and physical moving-body collisions wake it. A sleeping body skips unnecessary integration until acted upon and its earned stabilization and active sleeping population are included in replay evidence.

**5. Studio source visualizer.** Author-signed static fixtures now render their actual rotated geometry, and the physics HUD exposes sweep impacts, candidate load, pruned contacts, exact SAT test counts and sleeping bodies. This remains display-only; no canvas activity can mint game completion or change physics state.

## Adversarial proof and compatibility

- **16 regression tests** cover high-speed crossing rotating boxes, signed thin-fixture obstacles, rotation-only sweep, deep Z separation, disabled-policy differences, spatial hash stability and pruning, bounded sample ceilings, real resting surfaces, motor/impulse wake, tampered work counters, saving, and the unchanged legacy AABB path.
- The existing source editor contract test is extended from 34 to 40 settings.
- `.github/workflows/game-builder-advanced-system-engines.yml` explicitly compiles the new modules and executes the new suite on Windows and Ubuntu exact head, together with all earlier advanced-engine gameplay, legal source-scene and forged replay checks.
- **Prior milestone #3664** passed the complete advanced-engine test job on **both Ubuntu and Windows**, before this branch.
- **This milestone** must pass its own exact-head suite before its published implementation can be called validated. Do not substitute parent results for current branch results.

## Honest physics and performance bounds

Rotational contact here is **bounded temporal SAT sampling**, not mathematical continuous-time collision detection for rotating polygons. Extremely fast/thin grazing contacts can fall between samples; coherent multi-contact simultaneous impulse manifolds, true 3-axis quaternion shapes, arbitrary concave geometry, real deformable meshes and certified device benchmarking remain open. The broadphase is a bounded source-space acceleration for swept candidate detection, not an industry-scale ECS scheduler. Other game genres have not yet been rewired to use this physics runtime as their sole physical authority.

## Timestamped progress history

- **2026-10-12 — Advanced source physics:** executable finite 2D/3D bodies (improved: replaced configuration-only physics editor with signed game mechanics).
- **2026-10-12 — Continuous translational pairs and angular state:** (improved: pairs no longer pass through each other solely because endpoints do not overlap).
- **2026-10-12 — Oriented SAT contacts:** (improved: rectangular orientation changes physical collision outcomes, with actual contact normals).
- **2026-10-12 — This milestone:** (improved: intermediate rotational trajectories checked, signed broadphase pruning, supported-body settling and wake telemetry).
- **2026-10-12 — Verification gate:** append latest exact-head host results before review; independent Godot and consumer-device parity not yet established.

## Next substantive engine step

Prioritize native Godot physics export/parity for original scenes and establish replay comparison for the actual orientation, collision and sleep metadata. Then integrate the physics plane with vehicle/flight, platformer and authored world adapters, preserving one signed source and explicit rights/device gates.
