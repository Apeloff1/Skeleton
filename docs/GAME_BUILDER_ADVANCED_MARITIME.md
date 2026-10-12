# Advanced Original Maritime Game — Executable Reference

**Date (UTC):** 2026-10-12  
**Branch:** `feat/advanced-sailing-maritime-runtime-20261012`  
**Dependency:** [Game Builder #3642](https://github.com/Apeloff1/Skeleton/pull/3642)  
**Scope:** original deterministic reference gameplay, **not** certified Godot/native/hardware/commercial release.

## What is implemented

This engine is an actual turnable game, integrated into the canonical editor, authenticated local studio game command endpoint, signed authored scenes, replay receipts, savegame continuation and hybrid assembly source checks.

The `sailing` editor exposes **38 typed settings**: original world wind and sea state, sail efficiency, rowing, chart motion, storms, temporal weather transitions, ship displacement and cargo weight, dynamic water ingress, buoyancy limit, finite bilge pumping, physical hull and reef collisions, crew and survivor provisioning, paid dockside repairs and provisioning, finite fishing grounds, active pirate pursuit, cargo purchase/sale, route rescue, terminal expedition and nonterminal endless-world scenarios.

The engine has **19 registered actions** (including helm turn, sail, row, dock, unload/rescue, and bilge pump) plus source-chained, finite time advancement. Actions cannot directly mutate health, position, credits, objective flags, or source checksums. The source editor contains 43 families; this increment lifts one additional family to executable advanced reference status, increasing **20 to 21 of 43**.

### Controls and gameplay

- `port`, `starboard` alter one cardinal heading at a time.
- `sail` moves according to wind heading, sail rig, sail efficiency, sea severity, current and displacement. Direct headwinds or no wind can prevent propulsion. `row` advances one grid cell if oars are installed.
- `anchor`, `unanchor` prevent/permit movement; `reef_sails`, `full_sails`, `lower_sails` change wind propulsion and rough-weather damage.
- `dock` and `undock` require real port coordinates. `load` moves a good from the origin warehouse into a bounded hold; `deliver` deposits real goods at the destination, with explicitly limited payment.
- `rescue` requires the original survivor's location and a free berth; `disembark` requires the destination harbor. A rescue-only route can finish **without buying or delivering cargo**.
- `fish` consumes actual shoal stocks and gear; `resupply` consumes coin and finite harbor supplies; `repair` consumes paid dockside stock.
- `pump` spends crew provisions to reduce actual leaking floodwater, which can otherwise overload the ship and destroy the hull. A ship can sink from reef, shore, starvation, enemy or insufficient buoyancy.

All movement is integer-based with bounded geography, finite states and visible state-derived local rendering. Weather and opponents are deterministic from the seed and canonical progression. The physics represents an original discrete **simcade reference**, not a hydrodynamic CFD or buoyancy certification.

### Verified-path example for a deterministic unopposed original scenario

```python
from skeleton.ai.game_builder.advanced_gameplay_runtime import run_advanced_session, verify_advanced_session
from skeleton.ai.game_builder.advanced_level_scenes import make_advanced_scene

settings = {"dynamic_currents": False, "pirate_speed": 0}
route = (
    ["load"] * 3 + ["undock"] + ["row"] * 9 +
    ["starboard"] + ["row"] * 2 + ["rescue"] +
    ["port"] + ["row"] * 4 + ["starboard"] +
    ["row"] * 5 + ["dock", "deliver"]
)
scene = make_advanced_scene("sailing", settings)
session = run_advanced_session("sailing", settings, route, scene=scene)
assert verify_advanced_session(session, settings)
assert session["state"]["delivered"] == 3
assert session["state"]["passengers_ashore"] == 1
assert session["state"]["finished"]
```

This scripted route is a deterministic test fixture, not an externally observed human playtest. The studio and CLI accept the same source-bound action vocabulary and do not grant model write access.

## Source and assurance boundaries

1. `system_editors.py` validates unknown settings, bounds, types and document digests; operator review remains required to commit authored source into the studio.
2. `advanced_level_scenes.py` accepts exact original sea-chart coordinates and finite stocks, rejects blocked route topology/overlaps, binds scene to setting+seed checksum, and forbids executable geometry or foreign asset URLs.
3. `advanced_gameplay_runtime.py` reconstructs all commands from original reviewed source and issues chained state receipts per action. Client-reported victories, money and positions are not authoritative.
4. `advanced_gameplay_save.py` imports and continues only complete replay-verified saves. Mutable snapshots never become authority.
5. `system_editor_assembly.py` independently executes both base and source-bound smoke steps for the sailing adapter without claiming native-release certification.
6. `.github/workflows/game-builder-advanced-system-engines.yml` adds the source and adversarial suite to exact-head Ubuntu+Windows Python/Node checks.

## Remaining work

- Run exact-head cross-platform tests and resolve any regressions.
- Native Godot marine physics rendering, sound, controls and hardware-level export are **not implemented** in this increment.
- Multi-vessel AI formations, marine campaigns, full sailing instrumentation, weather routing, accessibility/playtest quality, and all-genre release assurance remain future production slices.
- Marine simulation does not assert actual commercial safety or physically accurate fluid dynamics.
- The stacked parent PR and repository-wide gates must be green before merging; keep this feature draft until that happens.

**Completion measurement:** 21/43 (48.8%) advanced reference gameplay families when this branch is included; 22/43 remain authoring-only. This is a family-count metric, not total app completion or native target readiness.
