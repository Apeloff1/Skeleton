# Game Frontier virtual GPS, surveyed game maps and frame/GDD continuity

**Scope:** Fictional worlds only. This is a game navigation and level-design
subsystem, NOT actual location collection or a terrestrial surveying workflow.
Source branch: `feature/game-frontier-p0-p3-20261019`. Status: deterministic
game-candidate source; real Godot/native game acceptance is still open.

## Ownership and separation

- **Game navigation:** `skeleton/jeeves/game_frontier_virtual_navigation.py`.
  Pure source math, no GNSS/OS permissions, network, IP lookup, browser
  geolocation, WGS84 data or real user coordinates.
- **Real-device GPS (separate, unused here):**
  `game_frontier_geoposition.py` and `frontend/app/frontier-navigation.tsx`.
  Those prior opt-in features are NOT called by fictional game navigation. They
  may not be silently activated to fill missing virtual ranging samples.
- **Signed GDD and frame history:** Existing canonical validator and
  `game_frontier_frame_coherence.py`, 30/50/60/120 FPS receipts, independent
  verifier A (SHA-256) and verifier B (temporal/identity/world-law).
- **RPG Studio authoring:** `skeleton/forge/game_frontier_studio.py` binds an
  optional GameMap to existing project/realm IDs, supplies authoring tools,
  and constructs a frame-based virtual navigation receipt from placed prefabs.
- **Jeeves game candidate:** `game_frontier.py` composes frame/virtual
  positioning only when explicitly supplied, preserving the real GPS
  redaction/consent path and preventing mixed source requests.
- **Forge renderer:** `skeleton/forge/game_frontier_godot.py` exports a
  source-only Godot virtual map GPS HUD/route line with an explicit fictional
  label. This is not an observed running Godot screenshot.

## Navigation and surveying contract

`GameMap`: world ID, realm ID, finite tile bounds, metres-per-tile, map
rotation, world origin and obstacles. World XYZ is converted into map grid
and back via an invertible rotation/translation transform. Pseudo-geodetic
latitude/longitude are **fictional local-planet indicators**, not GPS on Earth.

`VirtualBeacon` stations generate deterministic synthetic ranges with
bounded game noise. `solve_virtual_gps` requires >=4 visible noncoplanar
sources, solves a 3D range-difference linearized system, checks full
absolute-range residuals and rejects singular/low-information constellations.
Occluded/disabled beacons do not count toward availability. Realistic radio
signal multipath, clock drift and deep-space orbital dynamics are P1/P2 work.

`VirtualSurveyControl`/ `VirtualSurveySighting`: GDD-approved control
locations, true game-world station-to-actor bearings with uncertainty, and
optional vertical sighting angles. Surveyed XY uses an independent two-axis
line-intersection system, with residual and angular geometry checks.
Altitudes are distinguished as resolved vs approximate/unresolved. Survey and
virtual beacon fix must agree within declared combined uncertainty.

`map_route` is deterministic, bounded A* over authored walkable 4-way
tiles. Real climbing, water, flying, ethereal passage, vertical portals and
dynamic obstruction are **future engine-controlled route adapters**; they
must not be invented by this grid-only pathfinder.

## Per-frame continuity and AI source assurance

1. Canonical game engine/studio owns actor position, velocity and source
   asset ID; frame GDD binds the immutable world-law source digest.
2. Existing chunking computes frame-specific spatial cell membership;
   verifier A checks content hashing and verifier B checks monotone frame
   index/time, no missing objects, movement envelope, stable source identity
   and signed-GDD/world-law note references.
3. Virtual GPS uses exactly the actor pose that passes both verifiers.
   A mismatched actor, realm, map, project or prior frame fails closed.
4. Optional consecutive virtual GPS receipts form a second independent
   hash-linked chain: prior receipt and frame identity are revalidated,
   map identity may not silently change, and measured movement must agree
   with the actual verified actor movement plus uncertainty. Teleportation
   and legitimate realm transitions need explicit signed migration/portal
   authority, not a spoofed GPS position.
5. `compile_studio_frame` includes the navigation receipt in
   `gdd_ai_context.verified_virtual_navigation` with exact source GDD/frame
   and GPS hashes, tile/XYZ, uncertainty and human review requirement.
   `game_frontier.py` likewise exposes candidate-only fictional navigation
   evidence under `cognition.virtual_navigation_context`.
6. Existing AI and game/event pipelines do **not** execute navigation
   suggestions or auto-promote a between-frame note to GDD canon.
7. The secondary `game_frontier_realism.py` auditor independently
   re-hashes virtual navigation content, checks fictional-only custody,
   bounded map/range geometry, survey alignment and frame/GDD digest linkage.

## Test and qualification envelope

`tests/test_game_frontier_virtual_navigation.py` covers 3D trilateration,
route obstacles, 30/50/60/120 FPS, landmark XY/Z surveying, occluded/near-
singular beacons, inconsistent ranges, forged map identity, tampered hashes,
cross-frame navigation chain, RPG Studio context and candidate Godot HUD.

**Unclosed work:** actual running Godot HUD, native game engine per-frame
dispatcher/actor controllers, real chunk streams across all eras, non-grid
multiworld routes, game-world time synchronization and longform replay of
survey/AI context, profile tests at target frame rates, and current
signed-GDD approval mechanics for portals and evolving world maps.
No real GPS permission should be requested by the virtual game feature.
