"""
🌌 WORLDFORGE — Cosmic-Scale Procedural World Engine (2026).

A deterministic, seedable generator that spans FIVE scales — Region → Planet →
Star System → Galaxy → Cosmos — with a deep customization surface (sliders +
toggles + palette/climate presets + structure toggles for caves/castles/dungeons/
ruins…), a library of 100+ named presets, an AI loremaster, and a two-way bridge
to the Vault: parse a saved GAME's files, forge a matching world, and save it
back tagged "(WG) WORLD GENERATED".

Pure-python, no numpy. Same config ⇒ byte-identical world; neighbouring regions
tile seamlessly. Backward-compatible: GET/POST /region + /biomes + /lore unchanged.
"""
from __future__ import annotations

import re
import math
import hashlib
import uuid
from collections import Counter, OrderedDict
from datetime import datetime, timezone

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel

from core.databases import client as _MONGO
from routes.llm_router import route_complete

router = APIRouter(prefix="/api/worldforge", tags=["worldforge"])

import os
import logging
_log = logging.getLogger("worldforge")
_db = _MONGO[os.environ.get("DB_NAME", "test_database")]
_vault = _MONGO.codedock_vault          # bridge to CodeDock Vault (asset entries)

# ── World-gen engine moved to worldforge_core.py (2026-06 refactor). Re-exported
# here so routes + PIL render funcs (and worldforge_publish) keep their imports. ──
from .worldforge_core import (  # noqa: F401
    MAX_SIZE, SEA_LEVEL, BIOMES, WATER, PALETTES, CLIMATES, STRUCTURES, COSMIC, SCALES,
    WorldConfig, _palette_color, _elevation, _hydraulic_erode, _classify, _shade,
    _default_features, _build_planet, _place_structures, _build_cosmic, build_world,
    _koppen, _shannon, _hazards, _trade_routes, _tile_cost, _astar,
    _ECONOMY, _KOPPEN_TABLE, _SOIL_FERT, compute_systems,
    plate_points, plate_at, boundary_type,
    _h01, _smooth, _vnoise, _fbm, _ridged,
    _name, _astro_name, _explain_toponym,
    _shade_hex, _hue_of, _grid_arrays, _bilinear, _starfield, _cfont, _lerp_cmap, _fbm_field,
)



# ════════════════════════════════════════════════════════════════════════
#  ENDPOINTS — generation
# ════════════════════════════════════════════════════════════════════════
@router.get("/biomes")
async def list_biomes():
    return {"biomes": [{"id": k, **v} for k, v in BIOMES.items()], "count": len(BIOMES)}


@router.get("/scales")
async def list_scales():
    return {"scales": SCALES, "count": len(SCALES)}


@router.get("/palettes")
async def list_palettes():
    return {"palettes": [{"id": k, "overrides": len(v)} for k, v in PALETTES.items()],
            "climates": [{"id": k, **v} for k, v in CLIMATES.items()],
            "structures": [{"id": k, "icon": v["icon"]} for k, v in STRUCTURES.items()]}


@router.get("/options")
async def options_schema():
    """Full customization schema → the frontend renders this as a questionnaire."""
    sliders = [
        {"key": "size", "label": "World size", "min": 8, "max": MAX_SIZE, "step": 4, "default": 48},
        {"key": "noise_scale", "label": "Detail / zoom", "min": 0.02, "max": 0.3, "step": 0.01, "default": 0.08},
        {"key": "sea_level", "label": "Sea level", "min": 0.1, "max": 0.6, "step": 0.01, "default": 0.30},
        {"key": "mountain_level", "label": "Mountain height", "min": 0.55, "max": 0.9, "step": 0.01, "default": 0.72},
        {"key": "snow_level", "label": "Snow line", "min": 0.7, "max": 0.98, "step": 0.01, "default": 0.85},
        {"key": "moisture_bias", "label": "Moisture", "min": -0.4, "max": 0.4, "step": 0.02, "default": 0.0},
        {"key": "temperature_bias", "label": "Temperature", "min": -0.4, "max": 0.4, "step": 0.02, "default": 0.0},
        {"key": "warp_strength", "label": "Coastline chaos", "min": 0.0, "max": 3.0, "step": 0.1, "default": 1.6},
        {"key": "ridge_strength", "label": "Mountain sharpness", "min": 0.0, "max": 0.9, "step": 0.05, "default": 0.45},
        {"key": "octaves", "label": "Terrain roughness", "min": 2, "max": 7, "step": 1, "default": 5},
        {"key": "erosion", "label": "Erosion / smoothing", "min": 0.0, "max": 1.0, "step": 0.1, "default": 0.0},
        {"key": "river_density", "label": "River density", "min": 0.0, "max": 0.15, "step": 0.01, "default": 0.04},
        {"key": "lake_density", "label": "Lake density", "min": 0.2, "max": 1.2, "step": 0.1, "default": 0.6},
        {"key": "settlement_density", "label": "Structure density", "min": 0.0, "max": 3.0, "step": 0.25, "default": 1.0},
        {"key": "star_density", "label": "Star density (cosmic)", "min": 0.01, "max": 0.2, "step": 0.01, "default": 0.05},
        {"key": "nebula", "label": "Nebula amount (cosmic)", "min": 0.0, "max": 1.0, "step": 0.1, "default": 0.5},
    ]
    toggles = [{"key": k, "label": v.get("label", k.replace("_", " ").title()), "icon": v["icon"],
                "default": k in ("town", "village", "harbor", "farmstead")}
               for k, v in STRUCTURES.items()]
    return {
        "scales": SCALES,
        "palettes": list(PALETTES.keys()),
        "climates": list(CLIMATES.keys()),
        "sliders": sliders,
        "feature_toggles": toggles,
        "render_modes": {
            "region": ["cartographic", "atlas", "blueprint", "photoreal"],
            "planet": ["globe", "spin", "photoreal"],
            "system": ["nasa", "bloom"],
            "galaxy": ["nasa", "bloom"],
            "cosmos": ["nasa", "bloom"],
        },
        "alternatives": len(sliders) + len(toggles) + len(PALETTES) + len(CLIMATES) + len(SCALES),
    }


def _gen_presets():
    """100+ deterministic named presets (palette × climate × scale × feature combos)."""
    out = []
    adjectives = ["Northern", "Coastal", "Greater", "Lower", "Upper", "Western",
                  "Eastern", "Central", "Highland", "Lowland", "Continental", "Maritime"]
    nouns = ["Basin", "Frontier", "Province", "Reaches", "Steppe", "Plateau", "Marches",
             "Lowlands", "Delta", "Watershed", "Range", "Coast"]
    combos = [
        ("region", "natural", "temperate", ["town", "city", "harbor"]),
        ("region", "arid", "arid", ["ghost_town", "quarry", "mine"]),
        ("region", "frozen", "frozen", ["research_station", "cave_system", "basecamp"]),
        ("region", "volcanic", "volcanic", ["mine", "quarry", "observatory"]),
        ("region", "alien", "alien", ["research_station", "observatory", "cave_system"]),
        ("region", "verdant", "tropical", ["logging_camp", "village", "town"]),
        ("region", "oceanic", "oceanic", ["harbor", "fishing_village", "lighthouse"]),
        ("region", "toxic", "swamp", ["ghost_town", "cave_system", "research_station"]),
        ("planet", "natural", "temperate", ["town", "city"]),
        ("planet", "frozen", "frozen", ["basecamp", "research_station"]),
        ("system", "natural", "temperate", []),
        ("galaxy", "twilight", "temperate", []),
        ("cosmos", "twilight", "temperate", []),
    ]
    i = 0
    for scale, pal, clim, feats in combos:
        for k in range(8):
            i += 1
            nm = f"{adjectives[(i * 3) % len(adjectives)]} {nouns[(i * 5) % len(nouns)]}"
            out.append({
                "id": f"preset_{i:03d}",
                "name": nm,
                "scale": scale, "palette": pal, "climate": clim,
                "features": {f: True for f in feats},
                "seed": 1000 + i * 137,
            })
    return out


_PRESETS = _gen_presets()


@router.get("/presets")
async def list_presets(scale: str = Query("")):
    items = _PRESETS if not scale else [p for p in _PRESETS if p["scale"] == scale]
    return {"presets": items, "count": len(items), "total": len(_PRESETS)}


class RegionBody(BaseModel):
    seed: int = 1337
    size: int = 48
    rx: int = 0
    ry: int = 0
    scale: float = 0.08


@router.post("/region")
async def region_post(body: RegionBody):
    """Back-compat: build a default region from a seed."""
    return build_world(WorldConfig(seed=body.seed, size=body.size, rx=body.rx,
                                   ry=body.ry, noise_scale=body.scale, scale="region"))


@router.get("/region")
async def region_get(seed: int = Query(1337), size: int = Query(48, ge=8, le=MAX_SIZE),
                     rx: int = Query(0), ry: int = Query(0),
                     scale: float = Query(0.08, gt=0, le=0.5)):
    return build_world(WorldConfig(seed=seed, size=size, rx=rx, ry=ry,
                                   noise_scale=scale, scale="region"))


@router.post("/world")
async def world_post(cfg: WorldConfig):
    """★ Full cosmic-scale generation with the complete customization surface."""
    return build_world(cfg)


class LoreBody(BaseModel):
    seed: int = 1337
    size: int = 40
    rx: int = 0
    ry: int = 0
    scale: float = 0.07
    world_scale: str = "region"
    palette: str = "natural"
    climate: str = "temperate"


@router.post("/name-key")
async def name_key(body: LoreBody):
    """★ Scientific name key — explains the real-world toponymic etymology of every
    generated place name in a world (deterministic, no LLM). Educational + verifiable."""
    cfg = WorldConfig(seed=body.seed, size=body.size, rx=body.rx, ry=body.ry,
                      noise_scale=body.scale, scale=body.world_scale,
                      palette=body.palette, climate=body.climate)
    world = build_world(cfg)
    cosmic = body.world_scale in ("system", "galaxy", "cosmos")
    entries = []
    for p in world["pois"][:20]:
        nm = p.get("name", "")
        if cosmic:
            comps = [{"part": nm, "meaning": "real astronomical catalogue designation "
                      "(Bayer Greek-letter + constellation, or HD/HIP/Gliese/Kepler/TRAPPIST star "
                      "catalogue, or NGC/Messier/IC/UGC/Abell deep-sky catalogue)"}]
        else:
            comps = _explain_toponym(nm, p.get("b"))
        entries.append({"name": nm, "kind": p.get("kind"), "icon": p.get("icon"), "etymology": comps})
    note = ("These designations follow real astronomical cataloguing conventions."
            if cosmic else
            "These names follow real Earth toponymic conventions — descriptive roots "
            "(colour, material, flora, landform, or a founder's name) combined with generic "
            "geographic terms of Old English, Norse, Latin and Romance origin.")
    return {"name": world["name"], "scale": body.world_scale, "region_name": world["name"],
            "convention": note, "entries": entries, "count": len(entries)}



@router.post("/lore")
async def region_lore(body: LoreBody):
    """★ AI lore for a generated world (any scale), grounded in its real data."""
    r = build_world(WorldConfig(seed=body.seed, size=body.size, rx=body.rx, ry=body.ry,
                                noise_scale=body.scale, scale=body.world_scale,
                                palette=body.palette, climate=body.climate))
    top = ", ".join(f"{d['label']} {d['pct']}%" for d in r["distribution"][:4])
    settlements = ", ".join(f"{p['name']} ({p['kind']})" for p in r["pois"][:4]) or "no notable objects"
    s = r["stats"]
    cosmic = body.world_scale in ("system", "galaxy", "cosmos")
    # SOTA context: real climate class, biodiversity, busiest trade corridor & hazards
    climo = ""
    if not cosmic:
        k = r.get("koppen", {}); bio = r.get("biodiversity", {}); hz = r.get("hazards", {})
        corridor = (max(r.get("routes", []), key=lambda e: e.get("tiles", 0))
                    if r.get("routes") else None)
        climo = (f"CLIMATE: Köppen {k.get('code')} ({k.get('name')}) — {k.get('summary')}\n"
                 f"BIODIVERSITY: Shannon H'={bio.get('index')} ({bio.get('rating')}, {bio.get('richness')} biomes)\n"
                 f"HAZARDS: dominant risk {hz.get('overall')}\n"
                 + (f"BUSIEST CORRIDOR: {corridor['from']}↔{corridor['to']} ({corridor['tiles']} tiles)\n"
                    if corridor else ""))
    system = (
        "You are a planetary scientist and human-geographer writing a field briefing. "
        "STRICT REALISM DOCTRINE — 100% scientific realism ONLY: zero magic, fantasy races, "
        "Tolkien tropes, mythical creatures, gods or the supernatural. Explain EVERYTHING by "
        "real plate tectonics, climate science, hydrology, evolutionary biology, real geography "
        "and human agency (trade, agriculture, resource extraction, settlement). "
        + ("Use accurate astronomy/astrophysics and real exoplanet science for cosmic scales. "
           if cosmic else
           "Draw on NASA Earth-observation analogs (Landsat/MODIS/SRTM/Sentinel). ")
        + "Be vivid but grounded; never contradict the data."
    )
    prompt = (f"{'COSMIC REGION' if cosmic else 'REGION'}: {r['name']} (scale {body.world_scale})\n"
              f"COMPOSITION: {top}\n"
              + climo
              + (f"WATER: {s['water_pct']}% ({s['river_tiles']} rivers, {s['lakes']} lakes); land {s['land_pct']}%.\n"
                 if not cosmic else f"OCCUPIED: {s['land_pct']}% of space.\n")
              + f"NOTABLE: {settlements}\n\n"
              "Write: (1) a one-line factual tagline; (2) a 2-3 sentence geophysical/ecological "
              "overview that NAMES the Köppen class and reflects the biodiversity/hazard data; (3) ONE "
              "realistic exploration or fieldwork hook tied to a named place or the busiest trade "
              "corridor (survey, expedition, resource study — no quests for treasure/monsters). Under 120 words.")
    routed = await route_complete("reasoning", prompt, system=system, use_cache=True)
    lore = (routed.get("content") or "").strip()
    if not lore:
        return {"error": routed.get("error") or "lore model returned nothing", "name": r["name"]}
    return {"name": r["name"], "region": r["region"], "scale": body.world_scale,
            "lore": lore[:1500], "model": routed.get("model"),
            "summary": {"terrain": top, "settlements": [p["name"] for p in r["pois"][:4]],
                        "stats": r["stats"]}}


# ════════════════════════════════════════════════════════════════════════
#  VAULT BRIDGE — parse a saved GAME's files → forge a world → save (WG)
# ════════════════════════════════════════════════════════════════════════
_HEX_RE = re.compile(r"#([0-9a-fA-F]{6})\b")


def _config_from_game(gid: str, title: str, genre: str, brief: str, code: str) -> WorldConfig:
    """Parse a game's metadata + code into a WorldConfig (deterministic by game id)."""
    blob = f"{title} {genre} {brief}".lower()
    seed = int(hashlib.md5(gid.encode()).hexdigest()[:8], 16) % 9_000_000 + 1000
    # palette by dominant hue of the game's hex colours
    hues = [_hue_of(h) for h in _HEX_RE.findall(code or "")][:400]
    hues = [h for h in hues if h >= 0]
    palette = "natural"
    if hues:
        avg = sum(hues) / len(hues)
        palette = ("volcanic" if avg < 25 or avg > 330 else "arid" if avg < 65
                   else "verdant" if avg < 160 else "oceanic" if avg < 250 else "alien")
    # scale by theme
    if any(w in blob for w in ("space", "galaxy", "cosmic", "star", "orbit", "planet", "asteroid")):
        wscale = "galaxy" if "galaxy" in blob or "cosmic" in blob else "system"
    else:
        wscale = "region"
    # climate by theme
    climate = "temperate"
    for w, c in (("ice", "frozen"), ("snow", "frozen"), ("winter", "frozen"),
                 ("desert", "arid"), ("sand", "arid"), ("lava", "volcanic"), ("volcano", "volcanic"),
                 ("ocean", "oceanic"), ("sea", "oceanic"), ("water", "oceanic"),
                 ("jungle", "tropical"), ("forest", "tropical"), ("swamp", "swamp")):
        if w in blob:
            climate = c
            break
    # structures detected in the game (mapped to realistic settlement types)
    feats = {}
    _KW = {"city": "city", "town": "town", "village": "village", "harbor": "harbor",
           "harbour": "harbor", "port": "harbor", "mine": "mine", "quarry": "quarry",
           "observatory": "observatory", "lighthouse": "lighthouse", "cave": "cave_system",
           "camp": "basecamp", "farm": "farmstead", "logging": "logging_camp",
           "research": "research_station", "ruin": "ghost_town", "ghost": "ghost_town",
           "fish": "fishing_village", "weather": "weather_station"}
    for w, k in _KW.items():
        if w in blob:
            feats[k] = True
    if any(w in blob for w in ("rpg", "rogue", "adventure", "quest", "explore", "survival")):
        feats.update({"cave_system": True, "town": True, "research_station": True})
    if not feats:
        feats = {"town": True, "city": True, "harbor": True}
    return WorldConfig(scale=wscale, seed=seed, size=56, palette=palette, climate=climate,
                       features=feats, settlement_density=1.4)


@router.get("/sources")
async def list_sources(limit: int = Query(30, ge=1, le=80)):
    """List saveable GAME files that can seed a world (playables + Galaxy vault zips)."""
    playables = await _db.playables.find(
        {"status": "ready"}, {"_id": 0, "playable_id": 1, "title": 1, "genre": 1, "brief": 1}
    ).sort("created_at", -1).limit(limit).to_list(limit)
    games = [{"source": "playable", "id": p["playable_id"], "title": p.get("title", "Untitled"),
              "genre": p.get("genre", ""), "brief": (p.get("brief") or "")[:140]} for p in playables]
    galaxy = []
    try:
        gv = await _db.galaxy_vault.find({}, {"_id": 0}).sort("created_at", -1).limit(20).to_list(20)
        galaxy = [{"source": "galaxy", "id": g.get("vault_id") or g.get("build_id"),
                   "title": g.get("title", "Build"), "genre": g.get("genre", "")} for g in gv if g.get("title")]
    except Exception:
        galaxy = []
    return {"games": games + galaxy, "count": len(games) + len(galaxy)}


class FromGameBody(BaseModel):
    source: str = "playable"
    source_id: str = ""
    save: bool = True


@router.post("/from-game")
async def world_from_game(body: FromGameBody):
    """★ Parse a saved game's files, forge a matching world, and (optionally) save it
    back to the Vault tagged '(WG) WORLD GENERATED'."""
    gid = (body.source_id or "").strip()
    if not gid:
        raise HTTPException(400, "source_id required")
    title = genre = brief = code = ""
    if body.source == "playable":
        g = await _db.playables.find_one(
            {"playable_id": gid}, {"_id": 0, "title": 1, "genre": 1, "brief": 1, "html": 1})
        if not g:
            raise HTTPException(404, "game not found")
        title, genre, brief, code = g.get("title", ""), g.get("genre", ""), g.get("brief", ""), g.get("html", "")
    else:
        g = await _db.galaxy_vault.find_one({"$or": [{"vault_id": gid}, {"build_id": gid}]}, {"_id": 0})
        if not g:
            raise HTTPException(404, "build not found")
        title, genre, brief = g.get("title", ""), g.get("genre", ""), g.get("title", "")
    cfg = _config_from_game(gid, title, genre, brief, code)
    world = build_world(cfg)
    world_id = uuid.uuid4().hex
    doc = {
        "world_id": world_id, "source": body.source, "source_id": gid, "source_title": title,
        "name": world["name"], "scale": world["scale"], "palette": cfg.palette, "climate": cfg.climate,
        "config": cfg.model_dump(), "stats": world["stats"],
        "distribution": world["distribution"][:8], "pois": world["pois"],
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    vault_id = None
    if body.save:
        try:
            await _db.worldforge_worlds.insert_one(dict(doc))
            # bridge: a CodeDock Vault asset entry tagged (WG)
            vault_id = str(uuid.uuid4())
            await _vault.assets.insert_one({
                "id": vault_id, "name": f"(WG) {world['name']}",
                "description": f"WORLD GENERATED from '{title}' — {world['scale']} scale, "
                               f"{cfg.palette}/{cfg.climate}.",
                "asset_type": "world", "content_base64": None, "url": None,
                "tags": ["WG", "WORLD GENERATED", "worldforge", world["scale"], body.source],
                "metadata": {"world_id": world_id, "source_id": gid, "scale": world["scale"],
                             "stats": world["stats"]},
                "user_id": "default_user", "created_at": datetime.now(timezone.utc).isoformat(),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            })
        except Exception as _e:
            _log.warning("worldforge /from-game vault insert failed: %s", _e)
    return {"world_id": world_id, "vault_id": vault_id, "saved": bool(vault_id),
            "parsed_config": {"scale": cfg.scale, "palette": cfg.palette, "climate": cfg.climate,
                              "features": [k for k, v in cfg.features.items() if v], "seed": cfg.seed},
            "world": world}


@router.get("/worlds")
async def list_worlds(limit: int = Query(30, ge=1, le=80)):
    """List worlds generated from games (saved with the (WG) tag)."""
    rows = await _db.worldforge_worlds.find(
        {}, {"_id": 0, "grid": 0}).sort("created_at", -1).limit(limit).to_list(limit)
    return {"worlds": rows, "count": len(rows)}


@router.get("/worlds/{world_id}")
async def get_world(world_id: str):
    """Fetch a saved (WG) world and regenerate its full grid from the stored config."""
    doc = await _db.worldforge_worlds.find_one({"world_id": world_id}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "world not found")
    world = build_world(WorldConfig(**doc["config"]))
    return {"meta": doc, "world": world}



# ════════════════════════════════════════════════════════════════════════
#  🪐 MAGNIFICENT RENDER — numpy/PIL globe · relief · galaxy (PNG)
# ════════════════════════════════════════════════════════════════════════
# ── PIL render functions moved to worldforge_paint.py (2026-06 refactor). Re-exported
# so route handlers below keep their calls. _cfg_from_query + routes stay here. ──
from .worldforge_paint import (  # noqa: F401
    _render_world, _render_world_hi, _render_cartographic, _render_plates,
    _render_thematic, _render_globe, _render_cosmic_img, _atlas_overlays,
    _terrain_enhance, _render_atlas, _render_blueprint, _render_galaxy_nasa,
    _render_globe_gif, _render_export,
)

def _cfg_from_query(scale, seed, size, palette, climate, sea_level, mountain_level,
                    moisture_bias, temperature_bias, river_density, settlement_density, features):
    feats = {}
    for f in (features or "").split(","):
        f = f.strip().lower()
        if f:
            feats[f] = True
    return WorldConfig(scale=scale, seed=seed, size=size, palette=palette, climate=climate,
                       sea_level=sea_level, mountain_level=mountain_level,
                       moisture_bias=moisture_bias, temperature_bias=temperature_bias,
                       river_density=river_density, settlement_density=settlement_density,
                       features=feats)


@router.get("/render")
async def render_world(scale: str = Query("region"), seed: int = Query(1337),
                       size: int = Query(56, ge=16, le=MAX_SIZE), palette: str = Query("natural"),
                       climate: str = Query("temperate"), sea_level: float = Query(0.30),
                       mountain_level: float = Query(0.72), moisture_bias: float = Query(0.0),
                       temperature_bias: float = Query(0.0), river_density: float = Query(0.04),
                       settlement_density: float = Query(1.0), features: str = Query(""),
                       zoom: float = Query(1.0, ge=0.5, le=8.0),
                       pan_x: float = Query(0.0), pan_y: float = Query(0.0),
                       mode: str = Query("auto"),
                       layer: str = Query(""),
                       master: bool = Query(True),
                       q: str = Query("")):
    """★ Render a MAGNIFICENT image of a world (PNG). Modes:
    region → cartographic | atlas | blueprint ; planet → globe ;
    galaxy/cosmos → nasa (spiral) | bloom. Supports zoom + pan for deep detail.
    master=true (default) upscales to a 4096px master; pass master=false for fast preview thumbnails."""
    from fastapi.responses import Response
    from core.render_quality import upscale_png_bytes
    cfg = _cfg_from_query(scale, seed, size, palette, climate, sea_level, mountain_level,
                          moisture_bias, temperature_bias, river_density, settlement_density, features)
    cfg.zoom = zoom
    cfg.noise_scale = max(0.01, cfg.noise_scale / max(0.3, zoom))
    cfg.pan_x = pan_x; cfg.pan_y = pan_y
    if mode == "thematic":
        cfg.size = max(cfg.size, 72)
        try:
            world = build_world(cfg)
            png = await __import__("asyncio").to_thread(_render_thematic, world, cfg, layer or "elevation")
            if master:
                png = await __import__("asyncio").to_thread(upscale_png_bytes, png)
        except Exception as e:
            raise HTTPException(500, f"thematic render failed: {e}")
        return Response(content=png, media_type="image/png",
                        headers={"Cache-Control": "public, max-age=3600"})
    try:
        png = await __import__("asyncio").to_thread(_render_world_hi, cfg, mode)
        if master:
            png = await __import__("asyncio").to_thread(upscale_png_bytes, png)
    except Exception as e:
        raise HTTPException(500, f"render failed: {e}")
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})




# bounded in-process cache for the (slow) animated globe — keyed by config signature
_GIF_CACHE: "OrderedDict[str, bytes]" = OrderedDict()
_GIF_CACHE_MAX = 48


@router.get("/render.gif")
async def render_gif(scale: str = Query("planet"), seed: int = Query(1337),
                     size: int = Query(72, ge=32, le=MAX_SIZE), palette: str = Query("natural"),
                     climate: str = Query("temperate"), sea_level: float = Query(0.30),
                     mountain_level: float = Query(0.72), moisture_bias: float = Query(0.0),
                     temperature_bias: float = Query(0.0), river_density: float = Query(0.04),
                     settlement_density: float = Query(1.0), features: str = Query(""),
                     zoom: float = Query(1.0, ge=0.5, le=6.0),
                     q: str = Query("")):
    """★ Animated rotating GLOBE (looping GIF) — a living planet."""
    from fastapi.responses import Response
    cfg = _cfg_from_query("planet", seed, size, palette, climate, sea_level, mountain_level,
                          moisture_bias, temperature_bias, river_density, settlement_density, features)
    cfg.zoom = zoom
    sig = f"{seed}|{size}|{palette}|{climate}|{sea_level}|{mountain_level}|{moisture_bias}|{temperature_bias}|{river_density}|{settlement_density}|{features}|{zoom}"
    cached = _GIF_CACHE.get(sig)
    if cached is not None:
        _GIF_CACHE.move_to_end(sig)
        return Response(content=cached, media_type="image/gif",
                        headers={"Cache-Control": "public, max-age=86400", "X-Cache": "HIT"})
    try:
        gif = await __import__("asyncio").to_thread(_render_globe_gif, cfg)
    except Exception as e:
        raise HTTPException(500, f"gif render failed: {e}")
    _GIF_CACHE[sig] = gif
    _GIF_CACHE.move_to_end(sig)
    while len(_GIF_CACHE) > _GIF_CACHE_MAX:
        _GIF_CACHE.popitem(last=False)
    return Response(content=gif, media_type="image/gif",
                    headers={"Cache-Control": "public, max-age=86400", "X-Cache": "MISS"})


# ════════════════════════════════════════════════════════════════════════
#  📤 SHAREABLE EXPORT — high-res PNG with a branded footer cartouche
# ════════════════════════════════════════════════════════════════════════
@router.get("/export")
async def export_world(scale: str = Query("region"), seed: int = Query(1337),
                       size: int = Query(64, ge=16, le=MAX_SIZE), palette: str = Query("natural"),
                       climate: str = Query("temperate"), sea_level: float = Query(0.30),
                       mountain_level: float = Query(0.72), moisture_bias: float = Query(0.0),
                       temperature_bias: float = Query(0.0), river_density: float = Query(0.04),
                       settlement_density: float = Query(1.0), features: str = Query(""),
                       zoom: float = Query(1.0, ge=0.5, le=8.0),
                       pan_x: float = Query(0.0), pan_y: float = Query(0.0),
                       mode: str = Query("auto"), name: str = Query(""),
                       q: str = Query("")):
    """★ High-res (1536px) shareable PNG with a branded footer — for export / social."""
    from fastapi.responses import Response
    cfg = _cfg_from_query(scale, seed, size, palette, climate, sea_level, mountain_level,
                          moisture_bias, temperature_bias, river_density, settlement_density, features)
    cfg.zoom = zoom
    cfg.noise_scale = max(0.01, cfg.noise_scale / max(0.3, zoom))
    cfg.pan_x = pan_x; cfg.pan_y = pan_y
    cap = name or build_world(cfg)["name"]
    try:
        png = await __import__("asyncio").to_thread(_render_export, cfg, mode, cap)
    except Exception as e:
        raise HTTPException(500, f"export failed: {e}")
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", cap)[:40] or "world"
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600",
                             "Content-Disposition": f'inline; filename="{safe}_worldforge.png"'})


# ════════════════════════════════════════════════════════════════════════
#  🗺️ II.2 — NARRATIVE & QUEST GRAPH ENGINE (branching DAG + consistency)
# ════════════════════════════════════════════════════════════════════════
def _loose_json(raw: str):
    import json
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        parts = s.split("```")
        if len(parts) >= 2:
            s = parts[1]
        s = s[4:].strip() if s[:4].lower() == "json" else s.strip()
    try:
        return json.loads(s)
    except Exception:
        a, b = s.find("{"), s.rfind("}")
        if 0 <= a < b:
            try:
                return json.loads(s[a:b + 1])
            except Exception:
                return None
    return None


# NOTE: POST /api/worldforge/quest + its QuestBody moved to
#       routes/worldforge_publish.py (Worldforge Publishing split).


# ════════════════════════════════════════════════════════════════════════
#  🛰️ II.3 — GALACTIC-SCALE STREAMING (LOD chunk manifest + on-demand tiles)
# ════════════════════════════════════════════════════════════════════════
# NOTE: streaming endpoints moved to routes/worldforge_publish.py (split).
# ════════════════════════════════════════════════════════════════════════
#  📖 SCIENTIFIC MONOGRAPH — NASA-grade realistic planetary survey (async job)
# ════════════════════════════════════════════════════════════════════════
# NOTE: monograph + poster (async LLM/Nano-Banana publishing) moved to
#       routes/worldforge_publish.py (Worldforge Publishing split).


# ════════════════════════════════════════════════════════════════════════
#  ⛰️ HEIGHTMAP EXPORT — 16-bit grayscale elevation (game-engine ready)
# ════════════════════════════════════════════════════════════════════════
@router.get("/heightmap.png")
async def heightmap(scale: str = Query("region"), seed: int = Query(1337),
                    size: int = Query(64, ge=16, le=MAX_SIZE), palette: str = Query("natural"),
                    climate: str = Query("temperate"), zoom: float = Query(1.0, ge=0.5, le=8.0),
                    pan_x: float = Query(0.0), pan_y: float = Query(0.0)):
    """★ 16-bit grayscale heightmap PNG (1024²) — drop into Unity/Unreal/Godot terrain."""
    from fastapi.responses import Response
    wscale = scale if scale in ("region", "planet") else "region"
    cfg = WorldConfig(seed=seed, scale=wscale, size=size, palette=palette, climate=climate)
    cfg.zoom = zoom
    cfg.noise_scale = max(0.01, cfg.noise_scale / max(0.3, zoom))
    cfg.pan_x = pan_x; cfg.pan_y = pan_y

    def _gen():
        import io
        import numpy as np
        from PIL import Image
        _rgb, elev, _n = _grid_arrays(build_world(cfg))
        imf = Image.fromarray(np.clip(elev, 0, 1).astype(np.float32), mode="F").resize((1024, 1024), Image.BILINEAR)
        h16 = (np.asarray(imf) * 65535.0).astype(np.uint16)
        out = Image.fromarray(h16, mode="I;16")
        buf = io.BytesIO(); out.save(buf, format="PNG"); return buf.getvalue()

    try:
        png = await __import__("asyncio").to_thread(_gen)
    except Exception as e:
        raise HTTPException(500, f"heightmap failed: {e}")
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=86400",
                             "Content-Disposition": 'inline; filename="heightmap_16bit.png"'})


# ════════════════════════════════════════════════════════════════════════
#  🧱 LOD MIP-TILE PYRAMID — slippy-map {z}/{x}/{y} streaming tiles
# ════════════════════════════════════════════════════════════════════════
# NOTE: streaming endpoints moved to routes/worldforge_publish.py (split).
# ════════════════════════════════════════════════════════════════════════
#  🧪 AGENT + PHYSICS SIMULATION — deterministic settlement/ecology dynamics
# ════════════════════════════════════════════════════════════════════════
class SimBody(BaseModel):
    seed: int = 1337
    size: int = 48
    world_scale: str = "region"
    palette: str = "natural"
    climate: str = "temperate"
    ticks: int = 24


@router.post("/simulate")
async def simulate(body: SimBody):
    """★ Run a deterministic agent-based + physics simulation over a world: settlement
    populations grow on logistic carrying capacity (fertility × water), a seasonal climate
    stress term perturbs growth, and hubs found new settlements when they overflow."""
    import math
    wscale = body.world_scale if body.world_scale in ("region", "planet") else "region"
    cfg = WorldConfig(seed=body.seed, size=min(body.size, 64), scale=wscale,
                      palette=body.palette, climate=body.climate)
    cfg.clamp()
    world = build_world(cfg)
    ticks = max(4, min(body.ticks, 60))
    # realistic population priors per real settlement type
    base_pop = {"capital": 14000, "city": 9000, "town": 2600, "village": 700,
                "harbor": 5200, "fishing_village": 900, "farmstead": 250, "mine": 1100,
                "quarry": 600, "logging_camp": 500, "observatory": 120,
                "research_station": 180, "weather_station": 60, "lighthouse": 30,
                "ghost_town": 40, "cave_system": 0, "basecamp": 90}

    agents = []
    for i, p in enumerate(world["pois"][:14]):
        h = ((cfg.seed * 2654435761 + i * 40503 + hash(str(p.get("name", ""))) & 0xFFFF) % 0xFFFF) / 0xFFFF
        kind = p.get("kind", "town")
        agents.append({"name": p.get("name", f"site{i}"), "kind": kind, "x": p.get("x", 0), "y": p.get("y", 0),
                       "pop": float(base_pop.get(kind, 800)),
                       "fertility": round(0.45 + 0.5 * h, 3),
                       "water": round(0.3 + 0.7 * ((h * 7.0) % 1.0), 3)})

    series, events = [], []
    for t in range(ticks):
        climate_stress = 0.06 * math.sin(t / 4.0) + 0.0009 * t          # seasons + slow warming
        total = 0.0
        for a in agents:
            carrying = 30000.0 * a["fertility"] * (0.6 + 0.4 * a["water"])
            r = 0.05 * a["fertility"] * (0.8 + 0.4 * a["water"]) - climate_stress
            a["pop"] = max(50.0, a["pop"] + a["pop"] * r * (1.0 - a["pop"] / carrying))
            total += a["pop"]
        if t > 0 and t % 6 == 0 and len(agents) < 22:
            hub = max(agents, key=lambda z: z["pop"])
            if hub["pop"] > 0.7 * 30000.0 * hub["fertility"]:
                nh = ((cfg.seed + t * 7919 + hash(hub["name"])) & 0xFFFF) / 0xFFFF
                new_name = _name(cfg.seed ^ (t * 101 + hub["x"]), hub["x"], t,
                                 biome="grassland", kind="village")
                agents.append({"name": new_name, "kind": "village", "x": hub["x"], "y": hub["y"],
                               "pop": 300.0, "fertility": round(0.4 + 0.5 * nh, 3), "water": round(0.3 + 0.6 * nh, 3)})
                events.append({"tick": t, "type": "settlement_founded", "by": hub["name"], "name": new_name})
        series.append({"tick": t, "total_pop": int(total), "settlements": len(agents),
                       "climate_stress": round(climate_stress, 4)})

    agents_out = sorted([{**a, "pop": int(a["pop"])} for a in agents], key=lambda z: -z["pop"])
    return {
        "name": world["name"], "scale": wscale, "ticks": ticks,
        "series": series, "events": events, "agents": agents_out,
        "summary": {"final_pop": int(sum(a["pop"] for a in agents)), "settlements": len(agents),
                    "peak_pop": max(s["total_pop"] for s in series),
                    "founded": len([e for e in events if e["type"] == "settlement_founded"])},
    }



