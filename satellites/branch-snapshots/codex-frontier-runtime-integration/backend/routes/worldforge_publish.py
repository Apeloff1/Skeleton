"""
Worldforge Publishing — narrative/LLM endpoints split out of the (very large)
worldforge.py module. This is a one-way dependency: it imports the world
builder + config from routes.worldforge, and registers its own router on the
SAME /api/worldforge prefix (registered independently in routes_registry).

Currently hosts the branching-quest generator; monograph/poster/streaming
remain in worldforge.py and can migrate here in a later pass.
"""
from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from routes.llm_router import route_complete
from routes.worldforge import WorldConfig, build_world, _db, _log, _render_world_hi, MAX_SIZE

router = APIRouter(prefix="/api/worldforge", tags=["worldforge-publish"])


def _loose_json(raw: str):
    """Tolerant JSON extractor: strips ``` fences and falls back to the first
    {...} span when the model wraps the object in prose."""
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


class QuestBody(BaseModel):
    seed: int = 1337
    size: int = 48
    world_scale: str = "region"
    palette: str = "natural"
    climate: str = "temperate"
    arc: str = ""


@router.post("/quest")
async def world_quest(body: QuestBody):
    """★ Generate a branching QUEST GRAPH (DAG) grounded in a generated world's
    real places + terrain, then run a lore-consistency check on the result."""
    wscale = body.world_scale if body.world_scale in ("region", "planet") else "region"
    cfg = WorldConfig(seed=body.seed, size=min(body.size, 64), scale=wscale,
                      palette=body.palette, climate=body.climate)
    world = build_world(cfg)
    places = [p["name"] for p in world["pois"][:8]]
    top = ", ".join(d["label"] for d in world["distribution"][:5])
    system = ("You are a scientific expedition planner. STRICT REALISM DOCTRINE: 100% real-world "
              "scientific scenarios ONLY — no magic, monsters, treasure, gods or fantasy. Objectives "
              "must be plausible real fieldwork/human-agency goals (surveys, sampling, search-and-rescue, "
              "resource logistics, settlement, conservation, hazard response). Output ONLY strict "
              "minified JSON, no prose, no markdown.")
    prompt = (
        f"World: {world['name']} ({wscale}). Terrain: {top}. Climate {body.climate}.\n"
        f"Named places (use ONLY these for any location field): {', '.join(places) or 'the survey area'}.\n"
        + (f"Theme: {body.arc}\n" if body.arc else "")
        + 'Design a branching field expedition as a DAG. Return JSON exactly: '
          '{"title":str,"premise":str,"factions":[str,str],'
          '"nodes":[{"id":"n1","title":str,"location":<one of the named places>,'
          '"objective":str,"branches":[{"choice":str,"to":<node id>,"consequence":str}]}],'
          '"epilogue":str}. "factions" = two real stakeholder groups (e.g. a survey team and a '
          'mining consortium). Make 4-6 nodes forming a real branching graph (≥1 node reachable '
          'from two different branches), every location drawn from the list, every objective and '
          'consequence grounded in real geography, logistics and science.'
    )
    # SOTA handling: one strict-retry (cache-bypassed) if the model returns unparseable JSON
    routed = await route_complete("reasoning", prompt, system=system, use_cache=True)
    quest = _loose_json(routed.get("content") or "")
    if not isinstance(quest, dict):
        routed = await route_complete(
            "reasoning",
            prompt + "\n\nReturn ONLY the JSON object. No prose, no code fences.",
            system=system, use_cache=False)
        quest = _loose_json(routed.get("content") or "")
    if not isinstance(quest, dict):
        return {"error": routed.get("error") or "quest model returned unparseable output",
                "name": world["name"], "raw": (routed.get("content") or "")[:400]}
    nodes = quest.get("nodes") or []
    ids = {n.get("id") for n in nodes if isinstance(n, dict)}
    unknown, dangling = [], []
    pset = set(places)
    for nd in nodes:
        if not isinstance(nd, dict):
            continue
        loc = nd.get("location")
        if loc and pset and loc not in pset:
            unknown.append(loc)
        for br in (nd.get("branches") or []):
            if isinstance(br, dict) and br.get("to") and br["to"] not in ids:
                dangling.append(br["to"])
    return {
        "name": world["name"], "scale": wscale, "quest": quest,
        "model": routed.get("model"), "places": places,
        "consistency": {
            "unknown_locations": sorted(set(unknown)),
            "dangling_branches": sorted(set(dangling)),
            "node_count": len(nodes),
            "ok": not unknown and not dangling and len(nodes) >= 2,
        },
    }


# ════════════════════════════════════════════════════════════════════════
#  📚 MONOGRAPH + 🖼️ POSTER — async LLM/Nano-Banana publishing (moved here)
# ════════════════════════════════════════════════════════════════════════
_MONO_JOBS: dict = {}

MONOGRAPH_SYSTEM = (
    "You are a NASA/ESA-grade planetary cartographer and scientific world architect. Produce a "
    "rigorous, book-length scientific monograph about a procedurally generated world. CORE RULES "
    "(NON-NEGOTIABLE): 100% scientific realism — NO magic, NO fantasy races, NO Tolkien/high-fantasy "
    "tropes, NO mythical creatures, NO supernatural forces. Everything must be explainable by plate "
    "tectonics, climate science, evolutionary biology, real physical geography and human (or plausibly "
    "evolved Homo sapiens) agency. Draw exclusively on real Earth-observation analogs (Landsat, MODIS, "
    "SRTM, Sentinel, Blue Marble, Night Lights, ASTER) and real exoplanet science. MAXIMIZE density at "
    "every scale: the highest plausible number of biomes, rivers, settlements, resources and quantitative "
    "interconnections. Be BACKEND-FRIENDLY: use markdown tables, key-value parameter blocks and JSON-style "
    "data blocks alongside vivid, render-ready visual descriptions. Never write 'in summary'. Ground EVERY "
    "statement in the supplied world data and NEVER contradict it — only explain and enrich it with science."
)


def _monograph_prompt(world: dict, cfg: WorldConfig) -> str:
    biomes = "; ".join(f"{d['label']} {d['pct']}%" for d in world["distribution"])
    pois = "; ".join(f"{p['name']} ({p['kind']} @ x{p['x']},y{p['y']}; {p.get('economy', 'mixed')})" for p in world["pois"][:24]) or "none mapped"
    s = world["stats"]
    k = world.get("koppen", {}); bio = world.get("biodiversity", {}); hz = world.get("hazards", {})
    routes = world.get("routes", []); sysd = world.get("systems", {})
    corridor = max(routes, key=lambda e: e.get("tiles", 0)) if routes else None
    haz_txt = ", ".join(f"{n} {v['label']}" for n, v in hz.get("ratings", {}).items()) if hz else "n/a"
    tec = sysd.get("tectonics", {}); ins = sysd.get("insolation", {}); wnd = sysd.get("winds", {})
    cur = sysd.get("currents", {}); hyd = sysd.get("hydrology", {}); lit = sysd.get("lithology", {})
    rsc = sysd.get("resources", {}); soi = sysd.get("soil", {}); pop = sysd.get("population", {})
    systems = (
        f"Köppen climate class: {k.get('code')} — {k.get('name')} ({k.get('summary')}).\n"
        f"Biodiversity (Shannon H'): {bio.get('index')} — {bio.get('rating')}, {bio.get('richness')} land biomes, evenness {bio.get('evenness')}.\n"
        f"Natural hazards: {haz_txt}; dominant {hz.get('overall')}.\n"
        f"Plate tectonics: {tec.get('plates')} plates, {tec.get('primary_setting')} (boundary density {tec.get('boundary_density')}).\n"
        f"Insolation: axial tilt {ins.get('axial_tilt_deg')}°, mean annual temp {ins.get('mean_annual_temp_c')} °C, seasonal range {ins.get('seasonal_range_c')} °C, day length {ins.get('day_length_h')} h.\n"
        f"Atmosphere/oceans: {wnd.get('prevailing')}; {cur.get('regime')}.\n"
        f"Hydrology: {hyd.get('watersheds')} watersheds, max Strahler order {hyd.get('max_strahler_order')}, est. peak discharge {hyd.get('est_peak_discharge_m3s')} m³/s.\n"
        f"Lithology: {lit.get('dominant')} (provinces: {', '.join(lit.get('provinces', []))}).\n"
        f"Resources: {', '.join(rsc.get('deposits', []))}; arable {rsc.get('arable_pct')}%.\n"
        f"Soils: {soi.get('soil_class')} (fertility {soi.get('fertility_index')}).\n"
        f"Demographics: estimated population ≈ {pop.get('estimated_total')} ({pop.get('density_per_tile')}/tile).\n"
        f"Trade network: {len(routes)} least-cost corridors"
        + (f"; busiest = {corridor['from']}↔{corridor['to']} ({corridor['tiles']} tiles, cost {corridor['cost']}).\n" if corridor else ".\n")
    )
    return (
        "WORLD DATA (immutable canonical facts — never contradict, only enrich):\n"
        f"Name: {world['name']}\nScale: {cfg.scale}\nPalette/Climate: {cfg.palette}/{cfg.climate}\nSeed: {cfg.seed}\n"
        f"Grid: {world['size']}x{world['size']} cells — treat as a REAL cadastral/coordinate lattice.\n"
        f"Land/filled: {s['land_pct']}%  Water: {s['water_pct']}%  Rivers: {s.get('river_tiles', 0)} tiles  "
        f"Lakes: {s.get('lakes', 0)}  Biome count: {s.get('biomes', 0)}  Settlements/objects: {s.get('settlements', 0)}.\n"
        f"Biome composition: {biomes}\n"
        f"COMPUTED SYSTEMS (use these EXACT values — do not invent contradictory ones):\n{systems}"
        f"Settlements/objects (name, kind, grid x,y; primary economy): {pois}\n\n"
        f"Produce '{world['name']} — A Realistic Planetary Monograph'. Use EXACTLY these sections IN ORDER:\n"
        "1. Reference Data Analysis — confirm the exact layout, biome %s and settlement positions above.\n"
        "2. Planetary & Cosmic Context — structured parameter table (radius, gravity, axial tilt, day/year length, "
        "star type, atmospheric composition, habitable-zone confirmation) + Blue-Marble true/false-colour/night-lights description.\n"
        "3. Geology & Plate Tectonics — explain every terrain feature; rock provinces, fault lines, seismic/volcanic risk; "
        "tie settlement sites to geology.\n"
        "4. Climate & Atmosphere — Köppen class per zone; prevailing winds/ocean currents/orographics; quantitative "
        "temp+precip table for ≥6 named locations across seasons.\n"
        "5. Hydrology & Water Systems — per river/lake: watershed, discharge estimate, flood regime, sediment/delta.\n"
        "6. Biomes, Ecology & Biodiversity — map each colour zone/biome %; dominant species (plausible scientific names), "
        "trophic web, biodiversity + endemism, human-modification table.\n"
        "7. Human Geography, Settlements & Economy — MASTER TABLE (Name | Grid x,y | Est. Population | Primary Economy | "
        "Dominant Biome | Key Resources); EXPAND the listed settlements into a fuller realistic network with roads + "
        "trade routes following rivers/coasts.\n"
        "8. History & Culture — geography-driven timeline table; distinct cultures keyed to biomes/rivers/minerals; realistic naming.\n"
        "9. Politics, Infrastructure & Challenges — powers, chokepoints, environmental pressures, adaptation.\n"
        "10. NASA-Style Map & Render Instructions — true-colour, false-colour NDVI, shaded-relief, land-cover, night-lights; "
        "include 2-3 ready-to-use photorealistic image-generation prompts for THIS exact geography.\n"
        "11. Backend-Ready Data Exports — aggregate ALL tables + a JSON-style block with keys: planetary_params, biomes[], "
        "settlements[], climate[], resources[], hydrology, sim_params{flood_freq, yield_mod, seismic_zones}.\n"
        "12. Maximization Notes — list every extra layer/detail added beyond the base data.\n"
        "Use heavy tables, quantitative values, cross-references, and 'From the Surveyor's Log' / 'NASA Composite Caption' "
        "callout boxes. Be exhaustive and maximize data density."
    )


def _monograph_worker(job_id: str, cfg: WorldConfig):
    """Runs in a dedicated daemon thread (own event loop). Calls the LLM directly
    (bypassing the router's DB logging, whose motor client is bound to the main
    loop and would hang here) so the main server loop is never blocked."""
    import time
    import asyncio
    from routes.llm_router import EMERGENT_LLM_KEY, ROUTING_POLICY, MODEL_CATALOG
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    t0 = time.time()
    try:
        world = build_world(cfg)
        prompt = _monograph_prompt(world, cfg)
        ensemble = ROUTING_POLICY.get("creative", ["gpt-5.4"])

        async def _call():
            last = None
            for m in ensemble:
                prov = MODEL_CATALOG.get(m, {}).get("provider", "openai")
                try:
                    chat = LlmChat(api_key=EMERGENT_LLM_KEY, session_id=f"mono-{job_id[:8]}",
                                   system_message=MONOGRAPH_SYSTEM).with_model(prov, m)
                    resp = await asyncio.wait_for(chat.send_message(UserMessage(text=prompt)), timeout=300)
                    return (resp.content if hasattr(resp, "content") else str(resp)), m
                except Exception as e:
                    last = e
            raise last or RuntimeError("no model available")

        text, model = asyncio.run(_call())
        text = (text or "").strip()
        if not text:
            _MONO_JOBS[job_id] = {"status": "error", "error": "model returned nothing",
                                  "elapsed": round(time.time() - t0, 1)}
        else:
            _MONO_JOBS[job_id] = {"status": "done", "monograph": text, "model": model,
                                  "name": world["name"], "scale": cfg.scale, "elapsed": round(time.time() - t0, 1)}
    except Exception as e:
        _log.warning("monograph job %s failed: %s", job_id, e)
        _MONO_JOBS[job_id] = {"status": "error", "error": str(e), "elapsed": round(time.time() - t0, 1)}


class MonographBody(BaseModel):
    seed: int = 1337
    size: int = 56
    world_scale: str = "region"
    palette: str = "natural"
    climate: str = "temperate"


@router.post("/monograph/async")
async def monograph_async(body: MonographBody):
    """★ Kick a NASA-grade scientific monograph job (returns job_id; poll /monograph/job/{id})."""
    import threading
    cfg = WorldConfig(seed=body.seed, size=min(body.size, 72), scale=body.world_scale,
                      palette=body.palette, climate=body.climate)
    cfg.clamp()
    job_id = uuid.uuid4().hex
    _MONO_JOBS[job_id] = {"status": "pending"}
    if len(_MONO_JOBS) > 24:                      # cap the in-memory store
        for k in list(_MONO_JOBS.keys())[:-24]:
            _MONO_JOBS.pop(k, None)
    threading.Thread(target=_monograph_worker, args=(job_id, cfg), daemon=True).start()
    return {"job_id": job_id, "status": "pending"}


@router.get("/monograph/job/{job_id}")
async def monograph_job(job_id: str):
    j = _MONO_JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "unknown monograph job")
    return {"job_id": job_id, **j}


class MonographSaveBody(BaseModel):
    name: str = "World"
    scale: str = "region"
    seed: int = 0
    model: str = ""
    monograph: str


@router.post("/monograph/save")
async def monograph_save(body: MonographSaveBody):
    """★ Persist a generated monograph to the Worldforge Vault (shareable later)."""
    if not (body.monograph or "").strip():
        raise HTTPException(400, "empty monograph")
    mid = uuid.uuid4().hex[:12]
    doc = {"id": mid, "name": body.name, "scale": body.scale, "seed": body.seed,
           "model": body.model, "chars": len(body.monograph), "monograph": body.monograph,
           "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        await _db.worldforge_monographs.insert_one(dict(doc))
    except Exception as e:
        _log.warning("monograph save failed: %s", e)
        raise HTTPException(500, "save failed")
    return {"id": mid, "saved": True, "name": body.name, "chars": doc["chars"]}


@router.get("/monograph/saved")
async def monograph_saved():
    """★ List saved monographs (newest first, without the heavy body)."""
    rows = await _db.worldforge_monographs.find(
        {}, {"_id": 0, "monograph": 0}).sort("created_at", -1).limit(40).to_list(40)
    return {"items": rows, "count": len(rows)}


@router.get("/monograph/saved/{mid}")
async def monograph_saved_one(mid: str):
    doc = await _db.worldforge_monographs.find_one({"id": mid}, {"_id": 0})
    if not doc:
        raise HTTPException(404, "monograph not found")
    return doc


# ════════════════════════════════════════════════════════════════════════
#  🖼️ PHOTOREALISTIC POSTER — Gemini Nano-Banana render of the world (async)
# ════════════════════════════════════════════════════════════════════════
_POSTER_JOBS: dict = {}

_POSTER_STYLES = {
    "satellite": "Landsat-9 true-colour satellite orthophoto, 30 m/px, soft NW hillshade",
    "globe": "Blue-Marble orbital full-disk globe view from space with cloud bands and atmospheric limb",
    "relief": "grey-hypsometric shaded-relief topographic map with 100 m contours and NW illumination",
    "night": "NASA Black-Marble night-lights composite, dark land with warm settlement light necklaces along rivers and coasts",
}


def _poster_prompt(world: dict, cfg: WorldConfig, style: str) -> str:
    biomes = ", ".join(d["label"] for d in world["distribution"][:5]) or "mixed terrain"
    s = world["stats"]
    look = _POSTER_STYLES.get(style, _POSTER_STYLES["satellite"])
    return (
        f"Photorealistic NASA-grade {look} of a mid-latitude continental region named {world['name']}. "
        f"Dominant land cover: {biomes}. Land {s.get('land_pct', 60)}% / water {s.get('water_pct', 40)}%. "
        "Dark teal montane forest, silver glaciated uplands with radial blue river valleys, turquoise shallow "
        "delta bays, tan rain-shadow grassland, faint rectilinear farmland cadastre, subtle cumulus clouds. "
        "Scientifically accurate land-cover, no text, no labels, ultra-detailed, crisp, 8k, true-colour."
    )


def _poster_worker(job_id: str, cfg: WorldConfig, style: str):
    import time
    import asyncio
    from emergentintegrations.llm.chat import LlmChat, UserMessage
    t0 = time.time()
    try:
        world = build_world(cfg)
        prompt = _poster_prompt(world, cfg, style)
        key = os.environ.get("EMERGENT_LLM_KEY")

        async def _gen():
            chat = LlmChat(api_key=key, session_id=f"poster-{job_id[:8]}",
                           system_message="You generate photorealistic scientific Earth-observation map imagery.")
            chat.with_model("gemini", "gemini-3.1-flash-image-preview").with_params(modalities=["image", "text"])
            return await chat.send_message_multimodal_response(UserMessage(text=prompt))

        _txt, images = asyncio.run(_gen())
        if images:
            from core.render_quality import upscale_b64
            img0 = images[0]
            mime = img0.get("mime_type", "image/png")
            hi = upscale_b64(img0.get("data"))
            _POSTER_JOBS[job_id] = {"status": "done", "image": f"data:{mime};base64,{hi}",
                                    "prompt": prompt, "name": world["name"], "style": style,
                                    "elapsed": round(time.time() - t0, 1)}
        else:
            _POSTER_JOBS[job_id] = {"status": "error", "error": "no image returned", "prompt": prompt,
                                    "elapsed": round(time.time() - t0, 1)}
    except Exception as e:
        _log.warning("poster job %s failed: %s", job_id, e)
        _POSTER_JOBS[job_id] = {"status": "error", "error": str(e), "elapsed": round(time.time() - t0, 1)}


class PosterBody(BaseModel):
    seed: int = 1337
    size: int = 56
    world_scale: str = "region"
    palette: str = "natural"
    climate: str = "temperate"
    style: str = "satellite"


@router.post("/poster/async")
async def poster_async(body: PosterBody):
    """★ Kick a Nano-Banana photorealistic poster job (returns job_id; poll /poster/job/{id})."""
    import threading
    cfg = WorldConfig(seed=body.seed, size=min(body.size, 72), scale=body.world_scale,
                      palette=body.palette, climate=body.climate)
    cfg.clamp()
    job_id = uuid.uuid4().hex
    _POSTER_JOBS[job_id] = {"status": "pending"}
    if len(_POSTER_JOBS) > 24:
        for k in list(_POSTER_JOBS.keys())[:-24]:
            _POSTER_JOBS.pop(k, None)
    threading.Thread(target=_poster_worker, args=(job_id, cfg, body.style), daemon=True).start()
    return {"job_id": job_id, "status": "pending", "style": body.style}


@router.get("/poster/job/{job_id}")
async def poster_job(job_id: str):
    j = _POSTER_JOBS.get(job_id)
    if not j:
        raise HTTPException(404, "unknown poster job")
    return {"job_id": job_id, **j}


class PosterSaveBody(BaseModel):
    name: str = "World"
    scale: str = "region"
    seed: int = 0
    style: str = ""
    image: str


@router.post("/poster/save")
async def poster_save(body: PosterSaveBody):
    """★ Persist a generated poster (base64) to the Worldforge poster gallery."""
    if not (body.image or "").strip():
        raise HTTPException(400, "empty image")
    pid = uuid.uuid4().hex[:12]
    doc = {"id": pid, "name": body.name, "scale": body.scale, "seed": body.seed, "style": body.style,
           "image": body.image, "created_at": datetime.now(timezone.utc).isoformat()}
    try:
        await _db.worldforge_posters.insert_one(dict(doc))
    except Exception as e:
        _log.warning("poster save failed: %s", e)
        raise HTTPException(500, "save failed")
    return {"id": pid, "saved": True, "name": body.name}


@router.get("/poster/saved")
async def poster_saved():
    """★ Poster gallery (newest first, with images — capped for payload size)."""
    rows = await _db.worldforge_posters.find({}, {"_id": 0}).sort("created_at", -1).limit(12).to_list(12)
    return {"items": rows, "count": len(rows)}


# ════════════════════════════════════════════════════════════════════════
#  🛰️ GALACTIC-SCALE STREAMING — LOD manifest + on-demand tiles (moved here)
# ════════════════════════════════════════════════════════════════════════
@router.get("/stream/manifest")
async def stream_manifest(seed: int = Query(1337), scale: str = Query("region"),
                          size: int = Query(48, ge=16, le=MAX_SIZE), palette: str = Query("natural"),
                          climate: str = Query("temperate"), max_lod: int = Query(4, ge=1, le=6)):
    """★ Infinite-map manifest: LOD pyramid + addressable chunk grid for streaming."""
    wscale = scale if scale in ("region", "planet") else "region"
    cfg = WorldConfig(seed=seed, scale=wscale, size=size, palette=palette, climate=climate)
    world = build_world(cfg)
    lods = []
    for L in range(max_lod):
        zoom = 2 ** L
        lods.append({"lod": L, "zoom": zoom, "chunks_per_axis": zoom,
                     "total_chunks": zoom * zoom, "tile_px": 768,
                     "meters_per_tile": round(1000.0 / zoom, 1)})
    return {"seed": seed, "scale": wscale, "world_name": world["name"], "max_lod": max_lod,
            "tile_px": 768, "lods": lods,
            "total_addressable_chunks": sum(l["total_chunks"] for l in lods)}


@router.get("/stream/chunk.png")
async def stream_chunk(seed: int = Query(1337), scale: str = Query("region"),
                       lod: int = Query(0, ge=0, le=6), cx: int = Query(0), cy: int = Query(0),
                       size: int = Query(56, ge=16, le=MAX_SIZE), palette: str = Query("natural"),
                       climate: str = Query("temperate"), mode: str = Query("auto")):
    """★ Deterministic on-demand LOD tile for (lod, cx, cy) — the streaming unit."""
    from fastapi.responses import Response
    wscale = scale if scale in ("region", "planet") else "region"
    cfg = WorldConfig(seed=seed, scale=wscale, size=size, palette=palette, climate=climate)
    zoom = float(2 ** lod)
    cfg.zoom = zoom
    cfg.noise_scale = max(0.01, cfg.noise_scale / max(0.3, zoom))
    window = cfg.size / zoom
    cfg.pan_x = cx * window
    cfg.pan_y = cy * window
    try:
        png = await __import__("asyncio").to_thread(_render_world_hi, cfg, mode)
    except Exception as e:
        raise HTTPException(500, f"chunk render failed: {e}")
    return Response(content=png, media_type="image/png",
                    headers={"Cache-Control": "public, max-age=3600"})


@router.get("/stream/tile/{z}/{x}/{y}.png")
async def stream_tile(z: int, x: int, y: int, seed: int = Query(1337), scale: str = Query("region"),
                      size: int = Query(56, ge=16, le=MAX_SIZE), palette: str = Query("natural"),
                      climate: str = Query("temperate"), mode: str = Query("auto")):
    """★ Deterministic LOD mip-tile (z=zoom level → 2^z tiles/axis). Heavily cacheable."""
    from fastapi.responses import Response
    z = max(0, min(z, 6))
    n_tiles = 2 ** z
    x %= n_tiles; y %= n_tiles
    wscale = scale if scale in ("region", "planet") else "region"
    cfg = WorldConfig(seed=seed, scale=wscale, size=size, palette=palette, climate=climate)
    zoom = float(2 ** z)
    cfg.zoom = zoom
    cfg.noise_scale = max(0.01, cfg.noise_scale / max(0.3, zoom))
    window = cfg.size / zoom
    cfg.pan_x = x * window
    cfg.pan_y = y * window
    try:
        png = await __import__("asyncio").to_thread(_render_world_hi, cfg, mode)
    except Exception as e:
        raise HTTPException(500, f"tile render failed: {e}")
    return Response(content=png, media_type="image/png", headers={"Cache-Control": "public, max-age=86400"})
