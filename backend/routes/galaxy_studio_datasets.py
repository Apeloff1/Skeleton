"""
routes/galaxy_studio_datasets.py — Agent Self-Sufficiency Datasets (2026-06-18)

Emits large LOCAL reference datasets into every build so generative agents can
develop games while MINIMALLY relying on external systems. Each dataset is a
self-contained TS data module + a typed accessor; a registry indexes them all
and exposes an offline manifest.

Datasets (16 packs):
  algorithms · data_structures · design_patterns · engine_apis · shader_library ·
  net_protocols · physics_constants · math_utils · ai_heuristics · balance_curves ·
  audio_dsp · input_maps · localization_seed · security_recipes · procgen_recipes ·
  asset_catalogue

Self-contained: no import of routes.galaxy_studio.
"""
from __future__ import annotations
from typing import Dict, List

# Each dataset: (id, title, [entry tuples]) — entries become typed records.
DATASETS: List[dict] = [
    {"id": "algorithms", "title": "Algorithms", "kind": "knowledge",
     "entries": [
        ("a_star", "Best-first graph search with admissible heuristic", "O(E)", ["pathfinding", "navmesh"]),
        ("dijkstra", "Single-source shortest path, non-negative weights", "O(E+VlogV)", ["weighted_graph"]),
        ("quicksort", "Divide-and-conquer in-place sort", "O(n log n)", ["sorting"]),
        ("kd_tree", "Spatial partitioning for nearest-neighbour", "O(log n)", ["spatial", "collision"]),
        ("perlin_noise", "Gradient noise for terrain/texture", "O(1)/sample", ["procgen", "terrain"]),
        ("flood_fill", "Connected-region fill", "O(n)", ["procgen", "paint"]),
        ("minimax_ab", "Adversarial search with alpha-beta pruning", "O(b^(d/2))", ["ai", "board"]),
        ("rvo", "Reciprocal velocity obstacles for crowd avoidance", "O(n^2)", ["steering"]),
        ("marching_cubes", "Iso-surface extraction from scalar field", "O(n^3)", ["voxel", "mesh"]),
        ("wfc", "Wave function collapse tile synthesis", "O(n·k)", ["procgen"]),
     ]},
    {"id": "data_structures", "title": "Data Structures", "kind": "knowledge",
     "entries": [
        ("binary_heap", "Priority queue backing", "push/pop O(log n)", ["scheduling"]),
        ("quadtree", "2D spatial index", "query O(log n)", ["broadphase"]),
        ("octree", "3D spatial index", "query O(log n)", ["lod", "culling"]),
        ("sparse_set", "ECS component storage", "O(1)", ["ecs"]),
        ("ring_buffer", "Fixed-size FIFO", "O(1)", ["netcode", "audio"]),
        ("bitset", "Compact flag set", "O(1)", ["masks"]),
        ("trie", "Prefix tree for autocomplete", "O(k)", ["search"]),
        ("union_find", "Disjoint-set with path compression", "α(n)", ["connectivity"]),
     ]},
    {"id": "design_patterns", "title": "Design Patterns", "kind": "knowledge",
     "entries": [
        ("ecs", "Data-oriented entity-component-system", "decoupling", ["architecture"]),
        ("state_machine", "Explicit FSM for behaviour", "clarity", ["ai", "ui"]),
        ("observer", "Pub/sub event decoupling", "loose coupling", ["events"]),
        ("object_pool", "Reuse to avoid GC churn", "perf", ["memory"]),
        ("command", "Encapsulated actions for replay/undo", "replayability", ["input"]),
        ("flyweight", "Shared intrinsic state", "memory", ["assets"]),
        ("service_locator", "Central service registry", "access", ["systems"]),
        ("dirty_flag", "Defer expensive recompute", "perf", ["transform"]),
     ]},
    {"id": "engine_apis", "title": "Engine API Surface", "kind": "reference",
     "entries": [
        ("renderer.drawMesh", "Submit mesh with material + transform", "gpu", ["render"]),
        ("physics.raycast", "World raycast with layer mask", "query", ["physics"]),
        ("audio.play", "Play one-shot with mixer bus", "audio", ["sound"]),
        ("input.action", "Read mapped input action value", "input", ["controls"]),
        ("scene.load", "Async scene streaming", "io", ["streaming"]),
        ("ecs.query", "Iterate archetype matching components", "iter", ["ecs"]),
        ("net.send", "Reliable/unreliable channel send", "net", ["multiplayer"]),
        ("save.write", "Versioned persistent write", "io", ["save"]),
     ]},
    {"id": "shader_library", "title": "Shader Library", "kind": "snippet",
     "entries": [
        ("pbr_metallic", "Cook-Torrance metallic-roughness BRDF", "fragment", ["pbr"]),
        ("toon_ramp", "Cel-shading with ramp lookup", "fragment", ["stylized"]),
        ("water_gerstner", "Gerstner-wave vertex displacement", "vertex", ["water"]),
        ("grass_wind", "Vertex wind sway with noise", "vertex", ["foliage"]),
        ("fog_volumetric", "Ray-marched volumetric fog", "fragment", ["atmosphere"]),
        ("outline_normal", "Inverted-hull outline", "vertex", ["npr"]),
        ("dissolve", "Noise-threshold dissolve effect", "fragment", ["vfx"]),
        ("ssao", "Screen-space ambient occlusion", "post", ["ao"]),
     ]},
    {"id": "net_protocols", "title": "Net Protocols", "kind": "reference",
     "entries": [
        ("snapshot_interp", "Buffered snapshot interpolation", "100ms", ["sync"]),
        ("rollback", "Deterministic rollback netcode", "fighting", ["determinism"]),
        ("delta_compression", "State delta encoding", "bandwidth", ["compression"]),
        ("lockstep", "Deterministic lockstep simulation", "rts", ["determinism"]),
        ("client_prediction", "Predict + reconcile authoritative", "fps", ["latency"]),
        ("reliable_udp", "Ack/retransmit over UDP", "transport", ["transport"]),
     ]},
    {"id": "physics_constants", "title": "Physics Constants", "kind": "data",
     "entries": [
        ("gravity_earth", "9.81 m/s^2", "9.81", ["gravity"]),
        ("air_density", "1.225 kg/m^3 sea-level", "1.225", ["drag"]),
        ("restitution_rubber", "Bounciness ~0.83", "0.83", ["collision"]),
        ("friction_ice", "Kinetic friction ~0.03", "0.03", ["surface"]),
        ("terminal_velocity", "Human skydiver ~53 m/s", "53", ["fall"]),
        ("speed_sound", "343 m/s in air", "343", ["audio"]),
     ]},
    {"id": "math_utils", "title": "Math Utilities", "kind": "snippet",
     "entries": [
        ("lerp", "Linear interpolation", "a+(b-a)t", ["interp"]),
        ("smoothstep", "Hermite smoothing", "3t^2-2t^3", ["interp"]),
        ("slerp", "Spherical quaternion interpolation", "rotations", ["rotation"]),
        ("damp", "Frame-rate-independent damping", "exp", ["camera"]),
        ("remap", "Range remapping", "linear", ["scaling"]),
        ("noise2d", "Value noise 2D", "procgen", ["noise"]),
        ("pcg_hash", "PCG hash for reproducible RNG", "rng", ["random"]),
     ]},
    {"id": "ai_heuristics", "title": "AI Heuristics", "kind": "knowledge",
     "entries": [
        ("influence_map", "Spatial threat/opportunity field", "tactics", ["ai"]),
        ("utility_curves", "Response curves for decision scoring", "decisions", ["utility_ai"]),
        ("flocking_weights", "Separation/cohesion/alignment tuning", "crowds", ["steering"]),
        ("difficulty_dda", "Dynamic difficulty adjustment bands", "balance", ["director"]),
        ("goap_costs", "Action cost model for planning", "planning", ["goap"]),
        ("blackboard_keys", "Shared AI memory schema", "memory", ["bt"]),
     ]},
    {"id": "balance_curves", "title": "Balance Curves", "kind": "data",
     "entries": [
        ("xp_curve_exp", "Exponential XP-to-level", "1.15^n", ["progression"]),
        ("damage_softcap", "Diminishing returns past threshold", "soft", ["combat"]),
        ("economy_sink", "Currency drain vs faucet ratio", "0.7", ["economy"]),
        ("droprate_pity", "Pity-adjusted rarity probability", "pity", ["loot"]),
        ("ttk_target", "Target time-to-kill bands", "ms", ["combat"]),
        ("spawn_pacing", "Encounter density over time", "curve", ["pacing"]),
     ]},
    {"id": "audio_dsp", "title": "Audio DSP", "kind": "snippet",
     "entries": [
        ("reverb_schroeder", "Comb+allpass reverb", "fx", ["reverb"]),
        ("lowpass_biquad", "Biquad low-pass filter", "filter", ["eq"]),
        ("ducking_sidechain", "Sidechain compression for VO", "mix", ["mixer"]),
        ("doppler", "Pitch shift from relative velocity", "spatial", ["3d"]),
        ("adaptive_layers", "Vertical music layering", "music", ["adaptive"]),
     ]},
    {"id": "input_maps", "title": "Input Maps", "kind": "data",
     "entries": [
        ("gamepad_default", "Standard gamepad action map", "pad", ["controls"]),
        ("kbm_fps", "Keyboard+mouse FPS bindings", "kbm", ["controls"]),
        ("touch_virtual", "Virtual stick + buttons", "touch", ["mobile"]),
        ("accessibility_remap", "One-handed + toggle holds", "a11y", ["accessibility"]),
    ]},
    {"id": "localization_seed", "title": "Localization Seed", "kind": "data",
     "entries": [
        ("ui_core_en", "Core UI strings (English)", "en", ["i18n"]),
        ("plural_rules", "CLDR plural categories", "rules", ["i18n"]),
        ("rtl_langs", "Right-to-left language set", "rtl", ["i18n"]),
        ("number_formats", "Locale number/date formats", "fmt", ["i18n"]),
     ]},
    {"id": "security_recipes", "title": "Security Recipes", "kind": "knowledge",
     "entries": [
        ("save_hmac", "HMAC-signed save integrity", "integrity", ["anti_cheat"]),
        ("server_authoritative", "Authoritative state validation", "trust", ["netcode"]),
        ("rate_limit", "Token-bucket action rate limiting", "abuse", ["anti_cheat"]),
        ("obfuscation", "Constant/string obfuscation", "deterrent", ["client"]),
     ]},
    {"id": "procgen_recipes", "title": "ProcGen Recipes", "kind": "knowledge",
     "entries": [
        ("bsp_dungeon", "Binary-space-partition dungeon", "rooms", ["dungeon"]),
        ("cellular_cave", "Cellular automata caves", "caves", ["terrain"]),
        ("poisson_scatter", "Blue-noise object scatter", "scatter", ["decoration"]),
        ("l_system_flora", "L-system plant growth", "flora", ["foliage"]),
        ("graph_grammar_quest", "Quest graph grammar", "quests", ["narrative"]),
     ]},
    {"id": "asset_catalogue", "title": "Asset Catalogue", "kind": "data",
     "entries": [
        ("primitive_meshes", "Cube/sphere/capsule/plane set", "mesh", ["assets"]),
        ("material_presets", "PBR material presets", "material", ["assets"]),
        ("sfx_pack_core", "Core SFX set (UI/impact/foley)", "audio", ["assets"]),
        ("vfx_pack_core", "Core particle presets", "vfx", ["assets"]),
        ("font_set", "UI font ramp", "font", ["ui"]),
     ]},
]


def _camel(s: str) -> str:
    return ''.join(w.capitalize() for w in str(s).replace('-', '_').replace(' ', '_').split('_') if w)


def _gen_dataset_module(ds: dict, title: str, genre: str) -> str:
    cap = _camel(ds["id"])
    records = ",\n".join(
        "  { id: %r, summary: %r, meta: %r, tags: %r }" % (e[0], e[1], e[2], list(e[3]))
        for e in ds["entries"]
    )
    return f'''// {title} — Dataset: {ds["title"]} [{ds["kind"]}] | genre={genre}
// Local reference dataset — agents query this instead of external systems.

export interface {cap}Record {{ id: string; summary: string; meta: string; tags: string[]; }}

export const {ds["id"].upper()}_DATA: {cap}Record[] = [
{records}
];

const _index = new Map<string, {cap}Record>({ds["id"].upper()}_DATA.map((r) => [r.id, r] as const));

export function get{cap}(id: string): {cap}Record | undefined {{ return _index.get(id); }}
export function search{cap}(q: string): {cap}Record[] {{
  const s = q.toLowerCase();
  return {ds["id"].upper()}_DATA.filter((r) =>
    r.id.includes(s) || r.summary.toLowerCase().includes(s) || r.tags.some((t) => t.includes(s)));
}}
export function all{cap}(): {cap}Record[] {{ return {ds["id"].upper()}_DATA.slice(); }}
export const {ds["id"]}Meta = {{ id: '{ds["id"]}', title: '{ds["title"]}', kind: '{ds["kind"]}', count: {len(ds["entries"])} }};
'''


def _gen_dataset_registry(title: str, genre: str) -> str:
    imports = "\n".join(
        f"import {{ {ds['id'].upper()}_DATA, {ds['id']}Meta }} from './{_camel(ds['id'])}Dataset';"
        for ds in DATASETS
    )
    entries = "\n".join(
        f"  '{ds['id']}': {{ meta: {ds['id']}Meta, data: {ds['id'].upper()}_DATA }}," for ds in DATASETS
    )
    return f'''// {title} — DatasetRegistry | genre={genre}
// Offline knowledge fabric so agents develop with MINIMAL external dependencies.
{imports}

export const DATASET_REGISTRY = {{
{entries}
}} as const;

export const DATASET_IDS = Object.keys(DATASET_REGISTRY);
export const TOTAL_DATASETS = DATASET_IDS.length;
export const TOTAL_RECORDS = Object.values(DATASET_REGISTRY).reduce((a, d) => a + d.data.length, 0);

export function offlineManifest() {{
  return DATASET_IDS.map((id) => ({{ id, ...(DATASET_REGISTRY as any)[id].meta }}));
}}

/** Cross-dataset search — single entrypoint for agents. */
export function knowledgeSearch(q: string) {{
  const s = q.toLowerCase();
  const out: {{ dataset: string; id: string; summary: string }}[] = [];
  for (const id of DATASET_IDS) {{
    for (const r of (DATASET_REGISTRY as any)[id].data) {{
      if (r.id.includes(s) || r.summary.toLowerCase().includes(s) || r.tags.some((t: string) => t.includes(s)))
        out.push({{ dataset: id, id: r.id, summary: r.summary }});
    }}
  }}
  return out;
}}
'''


def get_dataset_catalog() -> dict:
    return {
        "ok": True,
        "total_datasets": len(DATASETS),
        "total_records": sum(len(d["entries"]) for d in DATASETS),
        "datasets": [
            {"id": d["id"], "title": d["title"], "kind": d["kind"], "count": len(d["entries"]),
             "sample": [e[0] for e in d["entries"][:5]]}
            for d in DATASETS
        ],
    }


def generate_datasets(build: dict, title: str, genre: str) -> Dict[str, str]:
    files: Dict[str, str] = {}
    try:
        for ds in DATASETS:
            files[f"data/datasets/{_camel(ds['id'])}Dataset.ts"] = _gen_dataset_module(ds, title, genre)
        files["data/datasets/DatasetRegistry.ts"] = _gen_dataset_registry(title, genre)
        if isinstance(build, dict):
            build["dataset_count"] = len(DATASETS)
            build["dataset_files"] = len(files)
            build["dataset_records"] = sum(len(d["entries"]) for d in DATASETS)
    except Exception as e:
        print(f"[GALAXY datasets] generation failed: {e}")
    return files
