# Forge Studio — 5,000 executable production operations

## What was built

The previous Forge Studio already had **500 directly implemented authoring
primitives and source-changing original-game producer algorithms**.

This change adds **4,500 additional executable *production workflows***
constructed as **10 independently addressable production domains × 50
existing authored archetypes × 9 source-changing treatments**.

**Total: 5,000 actual registered and executable commands.** The new
4,500 are **composed production recipes** rather than 4,500 unrelated
handwritten algorithms or complete finished games. The distinction is
intentional and visible to operators. None is a test or assurance gate.

Each recipe executes one or two real existing game editors and then an
additional treatment that changes map geometry, actor position/facing,
the native quest graph, or the RPG environmental conditions. Source
instances are typed, validated and preserved in the same canonical
`StudioProject` data as the previous 500. No parallel app or standalone
toy sample is introduced.

## Ten executable recipe domains

| Domain | Recipes | Executed game-production output |
|---|---:|---|
| `realm` | 450 | Original biomes, terrain, caves and sky geography: 50 biome algorithms + spatial production treatment |
| `architecture` | 450 | Settlements, infrastructure, castles and dungeons: 50 architectural tile algorithms + spatial production treatment |
| `population` | 450 | Characters, wildlife, armies and sky crews: 50 authored encounter populations + layout/facing treatment |
| `chronicle` | 450 | Narrative chapters, alternative routes and endings: 50 six-scene authored quest templates + branch detour |
| `atmosphere` | 450 | RPG weather, navigation, physics and social response: 50 environmental gameplay reactions + independent third sensor |
| `settlement` | 450 | Terrain + architecture in one world-authoring batch: 50 biome templates + 50 selected structure templates + two spatial treatments |
| `wildland` | 450 | Terrain + populated ecological worlds: 50 biome templates + 50 selected encounter templates + spatial and placement treatments |
| `stronghold` | 450 | Built structures + character/encounter placement: 50 architectural templates + 50 selected encounter templates + spatial and placement treatments |
| `expedition` | 450 | Native NPC encounters + playable questlines: 50 encounter templates + 50 selected six-scene quests + NPC layout and additional quest route |
| `living_story` | 450 | Quests + environmental RPG reactions: 50 playable quests + 50 sensor reactions + quest branch and third sensor |
| **Total** | **4,500** | **Real typed game-project mutations** |

Every domain owns exactly 50 source archetypes and nine treatments,
so each domain has 450 unique recipes. The catalog names have the
shape `produce_<domain>_<archetype>__<treatment>`, and the indexed
registry accepts only the exact 4,500 enumerated names.

## Nine real production treatments

| Treatment | Source-changing behavior |
|---|---|
| `waterways` | connected water-facing crossing and meandering spatial traversal; river depth observation for RPG reactions |
| `highlands` | elevated ridge geometry and placed actors with vertical height progression |
| `fortified` | bounded defensive perimeter geometry; inward-facing encounter perimeter |
| `nightfall` | sparse cover pattern and nocturnal character movement offsets |
| `festival` | open civic road grid and spectator courtyard population |
| `circuit` | service-lane grid and ordered worker/utility actor placements |
| `secrets` | obscured diagonal route, descending party poses and hidden objective |
| `skyreach` | walkable elevated ring and flying actor altitude changes |
| `wilderness` | irregular vegetated cover and decentralized creature distribution |

The real implementation executes different transforms depending on the
source content being produced. Map generators alter tile cell distributions;
encounters alter the actual generated `StudioPlacement` poses; quest
authors add reachable native stage branches with different objectives;
RPG-reactive scenes append an independently observed third condition.
Compositions apply the relevant typed effects to every authored component.

## Example authenticated project-production workflow

1. Open the existing Game Learning → Forge Studio tab.
2. Browse the new **4,500 production recipes** category.
3. Search `skyreach` or filter `expedition`; the server returns 32
   source-described recipes per page, never thousands of buttons.
4. Choose one operation, e.g.
   `produce_settlement_floating_islands__skyreach`.
5. The UI fills the actual map layer, prefab, seed, dimensions and an
   instance ID from existing authorized project metadata.
6. Queue the recipe with the *existing* production edit controls, preview
   all real source mutations, then commit using the exact scoped project
   revision and source digest.
7. The existing editor stores the new game layer(s), placements, quest
   stages and RPG pages in `game/editor/frontier_studio.json`.
8. The existing native expedition compiler consumes those source records
   for palette-backed Godot tile render geometry, traversable floor paths,
   world waypoints, native quest progression and RPG event proposals.

### Request example

```json
{
  "expected_version": 7,
  "expected_sha256": "<source-sha256-from-inspect>",
  "idempotency_key": "user-owned-unique-request-key",
  "steps": [
    {
      "action": "produce_expedition_sky_pirates__skyreach",
      "parameters": {
        "layer": "ground", "x": 0, "y": 0,
        "width": 12, "height": 12,
        "floor": 0, "wall": 1, "seed": 42,
        "prefab_id": "merchant", "count": 4,
        "radius": 8, "spacing": 2, "z": 0,
        "instance_id": "a"
      }
    }
  ]
}
```

The example identifiers are **illustrative** and require actual matching
layer/palette/prefab IDs in the saved project; the editor shows those live.

## Runtime architecture and performance

| Concern | Implemented integration |
|---|---|
| Source owner | Canonical immutable `StudioProject`; no parallel database |
| Runtime dispatch | `game_frontier_studio_authoring.py` with indexed `RECIPE_INDEX` lookup |
| Production compiler | `game_frontier_studio_production_recipes.py`, 10 domain plans |
| Mutation budget | Existing max 64 atomic user commands per batch; no unbounded internal recursion |
| Stable identities | `instance_id` (up to 16 bounded characters) namespaces repeated production runs |
| Storage | Existing tenant-scoped, versioned `save_editor` compare-and-set |
| Native game | Existing `compile_studio_expedition` and original Godot 4 scene emitter |
| Search API | Authenticated `GET /api/game-frontier-authoring/recipes` |
| Search controls | Query, domain, offset and 1–64 capped page size |
| Project summary | 500 core action identities; 4,500 recipe count; 5,000 total |
| UI | 25 existing editor groups plus searchable paginated recipe browser |
| Receipts | Per-user-operation before/after SHA-256 and entire batch evidence digest |
| Gate hygiene | No new quality gate, provider, source root or automatic release approval |

### Security and boundedness

Production plans are defined entirely on the trusted server; the user or
model cannot submit arbitrary embedded subcommands, callback functions,
dynamic source code, module paths or file destinations. Recipe parameters
accept a bounded allowlist of numeric/source-backed values and stable IDs.
Typed validators reject invalid layer geometry, prefab identities, duplicate
quests, non-finite sensors and unsupported event actions.

Recipes execute through the original authenticated project owner and
compare-and-set write. A failure within a composed recipe or larger user
batch leaves the **original source unchanged** until the host commits an
entire successful candidate.

This is a game-authoring toolset, not self-executing months-long autonomous
work: longer productions must use an authorized scheduler and persisted
project checkpoints.

## L00–L13 production handoff

| Level | Implementation |
|---|---|
| L00 | Preserve the single canonical Skeleton/Forge Studio app |
| L01 | Original source → producer plans → typed edits → versioned save → native compiler |
| L02 | 500 existing primitives, 4,500 new composite workflow contracts |
| L03 | Exact tool allowlist, project ID and host authorization |
| L04 | Spatial, NPC, quest and environment authored mutations |
| L05 | Immutable project data and canonical generation ownership |
| L06 | Bounded parameter shapes, no dynamic code or file execution |
| L07 | Fail on missing source, duplicate IDs, invalid/unsafe geometry |
| L08 | Hash-linked per-batch evidence and reproducible seeded recipes |
| L09 | Indexed dispatch; paginated discovery; bounded 64-step batches |
| L10 | Existing backend/Jeeves/React Native UI integration |
| L11 | 4,500 plan checks, 500 blueprint execution cases, 90 treatment cases |
| L12 | Host project revision history handles rollback and recovery |
| L13 | Native device operation, game completion, licensed rights and CI remain independent |

## Focused verification

```bash
python -m compileall -q skeleton/forge/game_frontier_studio*.py
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 PYTHONPATH=. \
  python -m pytest -q --noconftest \
  skeleton/testing/test_game_frontier_studio_production_5000.py
```

Exact-head CI qualification (including native Godot smoke and full app E2E)
must pass before merging. The 5,000 commands are **not a claim of 5,000
independent engine implementations, 5,000 finished games, or 5,000
commercial-quality full walkthroughs**.
