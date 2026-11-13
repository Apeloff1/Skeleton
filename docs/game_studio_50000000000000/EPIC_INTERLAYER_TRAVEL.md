# Epic multi-layer travel audit and controller handoff

## What is actually implemented

Epic variations can author up to eight existing material-coherent map layers in one immutable game-source transaction. This work adds the **source-side travel evidence** missing between the layered editor and the native Godot movement host:

- `skeleton/forge/game_frontier_studio_epic_route_graph.py`: traversability-aware four-neighbour BFS over actual typed `MapLayer` cells, plus explicit source-bound cross-layer transfer proposals. Reports full-path SHA-256 without truncation; only a bounded 128-point sample is returned for display.
- `backend/core/game_frontier_authoring.py`: rereads the canonical tenant-scoped project and independently replays the route witness. No new persistence layer, staged file, or provider tool.
- `backend/routes/game_frontier_authoring.py`: authenticated `POST /api/game-frontier-authoring/projects/{project_id}/epic-routes/audit` with the same ownership scope as Forge source inspection.
- `frontend/src/product/gameFrontierAuthoringClient.ts` and `frontend/src/features/Jeeves/GameFrontierEpicRoutePanel.tsx`: typed request, protocol validation, sample proposal generator, saved-version source SHA validation, distinct primary/alternative witnesses.
- `skeleton/testing/test_game_frontier_studio_epic_routes.py`: actual connection, blocked-tile, route-disjointness, one-way transfer, forged request and source-revision regression checks.

## Exact bounded request

```json
{
  "layer_ids": ["ground", "sky_island"],
  "connectors": [
    {
      "connector_id": "village_sky_lift",
      "from": {"layer": "ground", "x": 3, "y": 3},
      "to": {"layer": "sky_island", "x": 3, "y": 3},
      "mode": "elevator",
      "bidirectional": true
    }
  ],
  "itineraries": [
    {
      "journey_id": "story_to_sky",
      "start": {"layer": "ground", "x": 0, "y": 3},
      "goal": {"layer": "sky_island", "x": 6, "y": 3},
      "require_alternate": false
    }
  ]
}
```

There must be 1–8 unique original layer IDs, 0–64 candidate transfers, and 1–32 itineraries. Each link endpoint is an *actually traversable tile*, all IDs are format-checked, and connector modes are restricted to `walk`, `stairs`, `elevator`, `bridge`, `ferry`, `shuttle`, `portal`. Walking requires same-layer adjacent tiles. Bridges/walking must respect a small difference in elevation and distance; stairs are altitude-bounded. A `bidirectional: false` connector is a genuinely directional route, not a fictional implicit return.

## Graph and alternative proof

The witness uses BFS with deterministic neighbour order, respecting real material names from `game_frontier_studio_tile_navigation._traversable`. For an `require_alternate: true` itinerary, the second replay forbids interior nodes of the first route. The resulting accepted alternative is interior-vertex-disjoint from the primary route. An inaccessible tile or missing crossing reports failure; no unsafe automatic map editing or teleportation occurs. Each report includes source map checksums, the full project SHA, typed itinerary identity, complete-route SHA, limited preview samples, number of traversed connectors, failure reasons, and a report SHA.

If a designer edits the material palette or removes a passage, independently replay the identical itinerary across the previous and new source. `compare_epic_interlayer_routes` returns which specified journeys improved, regressed, or preserved reachability and rejects mismatched source scenarios or tampered checksums.

## Native runtime qualification and creative limits

**This is not a Godot playthrough.** A proposed portal, elevator or ferry is a signed navigation proposal; it does not animate, transport, load regions, or alter saved player state. To qualify a true Epic world the host must separately implement, approve and replay the real transport, collision, physics, camera, controller, save/load, NPC/quest continuity and cross-layer region streaming. An index of trillions of compositions represents an indexed source-recipe family, not trillions of complete games.
