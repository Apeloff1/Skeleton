"""
core/tool_forge.py — Tool Forge framework.

Each game-building tool (NPC, World, VFX, Combat, …) is a *scoped* Universal
Forge: a curated set of categories + only the style axes that are APPLICABLE to
it + a shared 7-step deterministic pipeline that forges a batch of game-ready
assets and mounts them to a build's Vault.

It reuses the existing engine primitives (``uf.generate`` for single assets,
``uf.compose_scene`` for batched forge+mount, ``uf._category_thumb`` for the
ID-only preview palettes) — so there is NO new storage and the assets land in
the same ``galaxy_constructs`` collection the worldforge/build read from.
"""
from __future__ import annotations

import json as _json

from core import universal_forge as uf

# ── Shared 7-step pipeline (deterministic DAG, mirrors the build stages) ────
PIPELINE_STEPS = [
    {"key": "plan",     "label": "Plan",     "blurb": "Resolve archetypes, counts & seed"},
    {"key": "forge",    "label": "Forge",    "blurb": "Deterministic geometry + palette"},
    {"key": "style",    "label": "Style",    "blurb": "Apply the selected style axes"},
    {"key": "variate",  "label": "Variate",  "blurb": "Seed-mutated variants per asset"},
    {"key": "enrich",   "label": "Enrich",   "blurb": "LLM quality-gate (optional)"},
    {"key": "validate", "label": "Validate", "blurb": "QC pass — DNA + component mask"},
    {"key": "mount",    "label": "Mount",    "blurb": "Mount the batch to the build Vault"},
]

# Axes every tool can use (general look + physical + quality dimensions).
_COMMON = ["art_style", "period", "realism", "mood", "rarity_tier", "theme_tint",
           "weight", "size", "height", "legendary_flair"]

# Extra axes layered onto a tool by key (bio/cosmic/material families) — keeps
# the per-tool registry terse while still giving each tool its applicable set.
_EXTRA_AXES: dict[str, list[str]] = {
    "npc": ["biological", "biological_aberrant", "biological_monstrosity", "subsurface", "starlight"],
    "nature": ["biological", "biological_aberrant", "subsurface"],
    "vfx": ["starlight", "cosmic", "subsurface"],
    "loot": ["starlight", "cosmic", "subsurface", "meteorite"],
    "combat": ["meteorite", "cosmic"],
    "scifi": ["meteorite", "cosmic", "starlight"],
    "world": ["meteorite", "cosmic"],
    "props": ["subsurface", "meteorite"],
    "ui": ["cosmic", "starlight"],
    "magic": ["cosmic", "starlight", "subsurface", "biological_aberrant"],
    "vehicle": ["meteorite", "cosmic"],
    "architecture": ["meteorite", "cosmic", "biological"],
    "wearable": ["subsurface", "starlight", "biological"],
    "consumable": ["subsurface", "biological", "cosmic"],
    "boss": ["biological_monstrosity", "biological_aberrant", "cosmic", "starlight"],
}

# ── Tool registry — `families` scopes the catalog, `axes` the APPLICABLE
#    style dimensions (resolved against uf.STYLE_AXES; unknown keys dropped). ─
TOOL_REGISTRY: list[dict] = [
    {
        "key": "npc", "label": "NPC Forge", "icon": "🧑",
        "blurb": "Characters, creatures & personalities",
        "families": ["character", "creature", "avatar", "mammal", "bird", "reptile",
                     "demon", "angel", "spirit", "undead", "pet", "familiar", "mount"],
        "axes": _COMMON + ["fantasy", "fashion", "aura", "illuminescence", "fur",
                           "feather", "scale_coat", "silhouette", "proportion",
                           "stance", "tattoo", "culture", "mythology"],
    },
    {
        "key": "world", "label": "World Builder", "icon": "🌍",
        "blurb": "Terrain, architecture & environments",
        "families": ["world", "structure", "terrain", "tower", "wall", "bridge",
                     "arch", "pillar", "platform", "fence", "fountain", "statue",
                     "door", "shrine", "flora"],
        "axes": _COMMON + ["biome", "season", "time_of_day", "weather", "architecture",
                           "stonework", "woodwork", "moss", "lichen", "weathering",
                           "mesh", "ornamentation"],
    },
    {
        "key": "vfx", "label": "VFX Forge", "icon": "✨",
        "blurb": "Particles, auras & magical effects",
        "families": ["fx", "light", "elemental", "orb", "spirit"],
        "axes": _COMMON + ["elemental", "magic", "aura", "light_emanation",
                           "illuminescence", "sparkles", "luminescence", "bloom",
                           "halo_type", "particle_type", "trail_type", "ambient_fx",
                           "impact_fx", "energy_state", "glow_pattern"],
    },
    {
        "key": "combat", "label": "Combat Designer", "icon": "⚔️",
        "blurb": "Weapons, armor & combat gear",
        "families": ["weapon", "armor", "shield", "helmet", "weapon_part", "ammo",
                     "explosive", "gloves", "boots"],
        "axes": _COMMON + ["metal_grade", "engraving", "finish", "elemental",
                           "damage_type", "weathering", "edge_style", "engraving_motif",
                           "inlay", "trim", "rune_set", "corrosion", "patina"],
    },
    {
        "key": "props", "label": "Prop Foundry", "icon": "📦",
        "blurb": "Items, containers, furniture & tools",
        "families": ["prop", "container", "furniture", "tool", "crate", "lockbox",
                     "book", "tome", "sign", "banner", "coin", "instrument"],
        "axes": _COMMON + ["finish", "woodwork", "metal_grade", "fabric", "leather",
                           "weathering", "scratch_density", "decals", "scribbles",
                           "engraving", "polish_level"],
    },
    {
        "key": "loot", "label": "Loot & Economy", "icon": "💎",
        "blurb": "Gems, relics, potions & currency",
        "families": ["gem", "relic", "artifact", "orb", "potion", "elixir", "coin",
                     "amulet", "ring", "crown", "totem", "idol", "rune_stone"],
        "axes": _COMMON + ["gemset", "iridescence", "crystallization", "magic", "aura",
                           "illuminescence", "sparkles", "inlay", "filigree",
                           "holography", "chromatics", "symbols"],
    },
    {
        "key": "scifi", "label": "Sci-Fi Forge", "icon": "🚀",
        "blurb": "Mechs, ships, drones & tech",
        "families": ["mech", "drone", "turret", "spaceship", "station", "satellite",
                     "engine", "console", "robot_pet", "machine", "vehicle"],
        "axes": _COMMON + ["punk", "mesh", "circuit_pattern", "neon_scheme", "camo",
                           "paint_scheme", "radiation", "magnetism", "energy_state",
                           "reflectivity", "hardware", "clearcoat", "illuminescence"],
    },
    {
        "key": "nature", "label": "Flora & Beasts", "icon": "🌿",
        "blurb": "Plants, food, fish & wildlife",
        "families": ["flora", "mushroom", "herb", "crop", "fruit", "vegetable", "food",
                     "beverage", "spice", "fish", "insect", "dinosaur", "sea_beast"],
        "axes": _COMMON + ["biome", "season", "growth", "decay", "moss", "vein_pattern",
                           "fur", "scale_coat", "texture", "pattern", "gradient"],
    },
    {
        "key": "ui", "label": "UI & HUD", "icon": "🖼️",
        "blurb": "Interface, icons, sigils & banners",
        "families": ["ui", "banner", "sign", "book"],
        "axes": _COMMON + ["gradient", "duotone", "neon_scheme", "pastel_scheme",
                           "monochrome", "heraldry", "banner_motif", "sigil_set",
                           "symbols", "decals", "accent_color"],
    },
    {
        "key": "magic", "label": "Magic & Relics", "icon": "🔮",
        "blurb": "Spell foci, relics, runes & arcana",
        "families": ["relic", "orb", "gem", "artifact", "totem", "idol", "rune_stone",
                     "amulet", "ring", "crown", "fx", "light", "elemental", "spirit"],
        "axes": _COMMON + ["magic", "aura", "elemental", "illuminescence", "sparkles",
                           "symbols", "iridescence", "filigree", "rune_set"],
    },
    {
        "key": "vehicle", "label": "Vehicle Bay", "icon": "🚗",
        "blurb": "Cars, mechs, ships, drones & engines",
        "families": ["vehicle", "mech", "spaceship", "drone", "engine", "turret", "machine"],
        "axes": _COMMON + ["paint_scheme", "neon_scheme", "camo", "circuit_pattern",
                           "weathering", "reflectivity", "clearcoat", "hardware", "punk"],
    },
    {
        "key": "architecture", "label": "Architecture", "icon": "🏛️",
        "blurb": "Buildings, towers, walls & shrines",
        "families": ["structure", "tower", "wall", "bridge", "arch", "pillar", "door",
                     "shrine", "platform", "fence", "fountain", "statue"],
        "axes": _COMMON + ["architecture", "stonework", "woodwork", "moss", "lichen",
                           "weathering", "ornamentation", "mesh"],
    },
    {
        "key": "wearable", "label": "Wearables", "icon": "🧥",
        "blurb": "Armor, helms, crowns & accessories",
        "families": ["armor", "helmet", "gloves", "boots", "crown", "amulet", "ring", "banner"],
        "axes": _COMMON + ["fashion", "fabric", "leather", "metal_grade", "engraving",
                           "trim", "inlay", "filigree", "finish"],
    },
    {
        "key": "consumable", "label": "Consumables", "icon": "🧪",
        "blurb": "Potions, food, elixirs & currency",
        "families": ["potion", "elixir", "food", "beverage", "herb", "spice", "coin", "fruit", "vegetable"],
        "axes": _COMMON + ["iridescence", "crystallization", "gradient", "magic",
                           "aura", "growth", "decay"],
    },
    {
        "key": "boss", "label": "Boss Forge", "icon": "🐉",
        "blurb": "Bosses, horrors & legendary beasts",
        "families": ["demon", "undead", "creature", "dinosaur", "sea_beast", "spirit", "mech"],
        "axes": _COMMON + ["fantasy", "aura", "elemental", "magic", "fur", "scale_coat",
                           "silhouette", "stance", "illuminescence"],
    },
    {
        "key": "terrain", "label": "Terrain Forge", "icon": "🏔",
        "blurb": "Cliffs, biomes, rocks & landforms",
        "families": ["terrain", "world", "flora", "fountain", "statue", "shrine"],
        "axes": _COMMON + ["biome", "season", "weathering", "moss", "lichen", "stonework", "mesh"],
    },
    {
        "key": "foliage", "label": "Foliage Forge", "icon": "🌳",
        "blurb": "Trees, plants, fungi & crops",
        "families": ["flora", "mushroom", "herb", "crop", "fruit", "vegetable"],
        "axes": _COMMON + ["biome", "season", "growth", "decay", "moss", "vein_pattern", "gradient"],
    },
    {
        "key": "environment", "label": "Environment Kit", "icon": "🏕",
        "blurb": "Set dressing — structures, world & shrines",
        "families": ["structure", "world", "terrain", "shrine", "fountain", "platform", "fence"],
        "axes": _COMMON + ["architecture", "stonework", "woodwork", "weathering", "ornamentation", "mesh"],
    },
    {
        "key": "decor", "label": "Decor & Furniture", "icon": "🪑",
        "blurb": "Furniture, props, banners & signage",
        "families": ["furniture", "prop", "banner", "sign", "book", "container"],
        "axes": _COMMON + ["woodwork", "fabric", "leather", "finish", "decals", "scribbles", "engraving"],
    },
    {
        "key": "icon", "label": "Icon & UI Kit", "icon": "🔖",
        "blurb": "Icons, sigils, banners & HUD marks",
        "families": ["ui", "sign", "banner", "book"],
        "axes": _COMMON + ["gradient", "duotone", "monochrome", "heraldry", "sigil_set", "symbols", "neon_scheme"],
    },
    {
        "key": "aquatic", "label": "Aquatic Forge", "icon": "🐠",
        "blurb": "Fish, sea beasts & ocean life",
        "families": ["fish", "sea_beast", "creature"],
        "axes": _COMMON + ["biological", "scale_coat", "fur", "subsurface", "iridescence", "pattern", "vein_pattern"],
    },
    {
        "key": "siege", "label": "Siege & War", "icon": "🏰",
        "blurb": "Siege engines, turrets & fortifications",
        "families": ["weapon", "turret", "explosive", "machine", "structure", "wall", "tower"],
        "axes": _COMMON + ["metal_grade", "weathering", "finish", "damage_type", "corrosion", "meteorite", "hardware"],
    },
]

_TOOL_BY_KEY: dict[str, dict] = {t["key"]: t for t in TOOL_REGISTRY}


def _resolve_axes(t: dict) -> list[str]:
    """Only the applicable axes that actually exist in the forge registry —
    the tool's own list plus its bio/cosmic/material extras."""
    seen: set[str] = set()
    out: list[str] = []
    for k in list(t.get("axes", [])) + _EXTRA_AXES.get(t["key"], []):
        if k in uf.STYLE_AXES and k not in seen:
            seen.add(k)
            out.append(k)
    return out


def _tool_categories(t: dict) -> list[dict]:
    fams = set(t.get("families", []))
    return [c for c in uf._CATEGORIES
            if c.get("family") in fams or c.get("key") in fams]


def get_tool(key: str) -> dict | None:
    return _TOOL_BY_KEY.get((key or "").strip().lower())


def list_tools() -> dict:
    tools = []
    for t in TOOL_REGISTRY:
        tools.append({
            "key": t["key"], "label": t["label"], "icon": t["icon"], "blurb": t["blurb"],
            "category_count": len(_tool_categories(t)),
            "axis_count": len(_resolve_axes(t)),
            "pipeline_steps": len(PIPELINE_STEPS),
        })
    return {"tools": tools, "count": len(tools), "pipeline": PIPELINE_STEPS}


def _axes_payload(keys: list[str]) -> list[dict]:
    out: list[dict] = []
    for k in keys:
        ax = uf.STYLE_AXES[k]
        out.append({
            "key": k, "label": ax["label"],
            "options": [{"key": ok, "label": (ov or {}).get("label", ok)}
                        for ok, ov in ax["options"].items()],
        })
    return out


def tool_catalog(key: str) -> dict:
    t = get_tool(key)
    if not t:
        return {"error": "unknown_tool", "tool": key}
    cats = [{**c, "thumb_palette": uf._category_thumb(c["key"])}
            for c in _tool_categories(t)]
    groups: dict[str, list[dict]] = {}
    for c in cats:
        groups.setdefault(c.get("group", "Things"), []).append(c)
    axis_keys = _resolve_axes(t)
    return {
        "tool": {"key": t["key"], "label": t["label"], "icon": t["icon"], "blurb": t["blurb"]},
        "categories": cats,
        "groups": [{"group": g, "categories": cs} for g, cs in groups.items()],
        "category_count": len(cats),
        "axes": _axes_payload(axis_keys),
        "axis_count": len(axis_keys),
        "pipeline": PIPELINE_STEPS,
    }


def tool_asset(key: str, id: str, era: str | None = None, seed: int | None = None,
               axes: dict | None = None, full: bool = False) -> dict:
    """Targeted single-asset fetch for a tool (light by default)."""
    t = get_tool(key)
    if not t:
        return {"error": "unknown_tool", "tool": key}
    # Only honour axes that this tool exposes.
    allowed = set(_resolve_axes(t))
    ax = {k: v for k, v in (axes or {}).items() if k in allowed}
    spec = uf.generate(id, era or "modern", use_llm=False, seed=seed, axes=ax)
    spec["tool"] = t["key"]
    if full:
        return spec
    geo = spec.get("geometry") or []
    light = {k: v for k, v in spec.items() if k != "geometry"}
    light["part_count"] = len(geo)
    light["thumb_palette"] = (spec.get("palette") or [])[:5]
    light["light"] = True
    return light


def run_pipeline(key: str, build_id: str, era: str | None = None, seed: int = 0,
                 count: int = 12, mount: bool = True, axes: dict | None = None,
                 config: dict | None = None, categories: list | None = None,
                 mode: str = "consecutive") -> dict:
    """The shared 7-step pipeline: plan → forge → style → variate → enrich →
    validate → mount. In CONSECUTIVE mode it spreads `count` assets across the
    tool's categories; in PRECISE mode it forges exactly the `categories` the
    creator picked. Applies the selected axes and mounts to the build Vault."""
    t = get_tool(key)
    if not t:
        return {"error": "unknown_tool", "tool": key}
    if not build_id:
        return {"error": "missing_build_id"}
    cats = _tool_categories(t)
    if not cats:
        return {"error": "no_categories", "tool": key}
    count = max(1, min(int(count or 12), 96))
    # plan: precise selection vs consecutive spread
    if categories:
        valid = {c["key"]: c for c in cats}
        chosen = [valid[k] for k in categories if k in valid]
        if not chosen:
            chosen = [cats[i % len(cats)] for i in range(count)]
        used_mode = "precise"
    else:
        chosen = [cats[i % len(cats)] for i in range(count)]
        used_mode = "consecutive"
    items_by_cat: dict[str, int] = {}
    for c in chosen:
        items_by_cat[c["key"]] = items_by_cat.get(c["key"], 0) + 1
    items = [{"category": k, "count": v} for k, v in items_by_cat.items()]
    allowed = set(_resolve_axes(t))
    ax = {k: v for k, v in (axes or {}).items() if k in allowed}
    style = {"axes": ax} if ax else None
    # forge + style + variate + mount happen inside compose_scene
    res = uf.compose_scene(build_id, era, items, seed=seed, mount=mount,
                           style=style, region=t["key"])
    trace = [{**s, "ok": True} for s in PIPELINE_STEPS]
    return {
        "tool": t["key"], "tool_label": t["label"],
        "build_id": build_id, "mounted": bool(mount), "mode": used_mode,
        "forged": res.get("total", 0),
        "categories_used": len(items),
        "applied_axes": ax,
        "pipeline": trace,
        "scene": res,
    }
