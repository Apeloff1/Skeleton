# World Codex v3: 192 design axes and sky-island worlds

## Contract and compatibility

The established 128 controls (16 domains, eight axes each) remain in exactly
the same order. Their existing decimal indices, v2 schema and source digests
remain stable. The versioned extension adds 64 separately indexed 8-bit
controls (eight new domains). A zero extension preserves the v2 identity.
Nonzero extended settings use a new reversible high-order 512-bit address
component and v3 digest, so existing IDs are never silently reinterpreted.
All external identities are decimal strings; never use JavaScript numbers.

The two layers are intentionally complementary: the older 24-axis 16-level
genomic-world design still contains its original `sky_islands` value; the
new Codex control is a higher-fidelity editable world-production parameter.

## Additional domains (8 × 8 controls)

- **Aerial realms:** sky_islands, cloud_oceans, suspended_archipelagos,
  skybridge_density, thermal_updrafts, aether_buoyancy,
  floating_settlements, aerial_isolation
- **Subterranean:** deep_strata, cavern_ecosystems, magma_tides,
  underground_rivers, crystal_growth, tectonic_ruptures, fungal_forests,
  ancient_vaults
- **Ocean systems:** coral_cities, abyssal_trenches, kelp_continents,
  underwater_currents, tidal_megafauna, submarine_ruins, floating_ports,
  deepwater_pressure
- **Atmosphere:** jet_streams, wind_shear, supercell_frequency,
  aurora_cycles, atmospheric_layers, sky_visibility, lightning_density,
  cloud_ecology
- **Mobility:** glider_lift, airship_lanes, climbing_networks,
  vertical_transit, grappling_routes, amphibious_travel, tunnel_networks,
  fast_travel_cost
- **Population:** npc_population_density, settlement_interdependence,
  migration_corridors, creature_sociality, civic_conflict,
  wilderness_encroachment, trade_route_activity, faction_memory_depth
- **Cinematic:** camera_parallax, horizon_depth, volumetric_lighting,
  shadow_complexity, atmospheric_perspective, environmental_animation,
  weather_reactivity, scene_transition_density
- **Simulation:** ecological_feedback, physical_weather_coupling,
  construction_integrity, dynamic_path_reconfiguration,
  terrain_erosion_rate, seasonal_resource_cycle, consequence_persistence,
  recovery_complexity

Each control has 256 explicit values (0–255). All 64 contribute to
domain terrain fields, individually executable `study_*` progress actions,
and native content-plan parameter selection. Eight additional earned
time-window traversal gates serve the new domains.

## Sky islands are world geometry, not a renamed axis

`sky_islands` and `cloud_oceans` influence deterministic elevated-cell
presence, altitude bands and cloud depth; `wind_shear`,
`aerial_isolation`, `skybridge_density` and trained `glider_lift`
change aerial risk and reachability. `cross_sky_islands` requires
appropriate earned skill and a time window. Dense islands lacking
skybridges also require two real glider training actions. Their gateway
actually changes the Codex state altitude and traversed route history.

The Codex produces four extra original tile archetypes for extended worlds:
`sky_island`, `cloud_sea`, `sky_port`, `aerial_bridge`. NES and
Game Boy output use genuine 2bpp bitplanes; SNES uses 4bpp bitplanes, with
encode/decode roundtrip verification. Existing v2 tile lists stay unchanged.

C99 desktop source generation now supports 192 trainable axes, 24
gates, an aerial altitude mechanic and the skybridge/glider condition.
The platform content compiler can select and quantize the extra domains
and include elevated traversal features in generated room data.

Eight coupled, bounded interaction metrics model initial cross-domain
pressure (aerial habitation/trade, subterranean/ocean risk, population,
cinematic scene depth, environmental response and social persistence).
These are deterministic simulation descriptors, not trained AI or
a commercial renderer.

## Authenticated world-design API

`POST /api/dragon-academy/native/production/worlds/codex/edit`

```json
{
  "index": "0",
  "changes": {
    "sky_islands": 188,
    "cloud_oceans": 132,
    "skybridge_density": 64,
    "glider_lift": 170,
    "wind_shear": 110,
    "floating_settlements": 120,
    "camera_parallax": 175
  }
}
```

Use the same request at
`POST /api/dragon-academy/native/production/worlds/codex/impact`
to compare old/new terrain, route requirements and source-generated NES
tile hashes before using the new exact decimal address. Editor authority
is required; unknown axes, bool levels, malformed addresses and forged
source identities fail closed.

`GET /api/dragon-academy/native/production/worlds/codex/capabilities`
returns all 24 grouped domains plus the legacy and extension identity ranges.

## Verification and honest limits

Focused regressions cover v2 address/digest stability, extended-axis
roundtrips and tamper rejection, real sky-island gate unlocking/replay,
native NES/SNES bitplane verification, protected API exposure, C99 source
generation and platform-projection evidence.

This patch **does not** claim executable ROM compilation, full 3D
renderer physics, all console toolchains, measured performance on target
hardware, playtested world fun, or shipped original titles. Native
hardware evidence must be established independently before release.
