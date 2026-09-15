"""Worldforge Earth-systems — SOTA hyper-realism geophysical/ecological models.

Extracted from worldforge.py (Session 13e refactor) AND extended with a full suite
of deterministic, scientifically-grounded planetary systems. Every model is a real
Earth-system simplification (plate tectonics, insolation, atmospheric circulation,
ocean gyres, hydrology/Strahler, lithology, economic geology, pedology, demographics)
so a generated world is internally consistent from bedrock to population. Pure leaf
module: depends only on stdlib + the noise PRNG.

Hyper-realism systems (10 steps):
  1. Köppen–Geiger climate            (_koppen)
  2. Plate tectonics & boundaries     (_plates)
  3. Insolation / axial tilt / seasons(_insolation)
  4. Atmospheric circulation & winds  (_winds)
  5. Ocean surface currents (gyres)   (_currents)
  6. Hydrology & Strahler stream order (_hydrology)
  7. Lithology / rock provinces        (_lithology)
  8. Economic geology / resources      (_resources)
  9. Pedology / soil fertility         (_soil)
 10. Carrying-capacity demographics    (_population)
Plus biodiversity (_shannon), natural hazards (_hazards, now plate-driven) and the
least-cost trade-route network (_trade_routes) carried over from earlier sessions.
"""
from __future__ import annotations

import math

from .worldforge_noise import _h01

# ── 1. Köppen–Geiger climate ─────────────────────────────────────────────
_KOPPEN_TABLE = {
    "tropical_forest": ("Af", "Tropical rainforest", "Hot and wet all year — every month exceeds 60 mm of rain."),
    "savanna": ("Aw", "Tropical savanna", "Hot, with a pronounced dry season driving grass–tree mosaics."),
    "desert": ("BWh", "Hot desert", "Arid — potential evaporation far exceeds the sparse rainfall."),
    "shrubland": ("BSk", "Cold semi-arid steppe", "Semi-arid scrub; drought-tolerant shrubs over thin soils."),
    "grassland": ("Cfa", "Humid subtropical", "Warm humid summers, mild winters — productive temperate plains."),
    "temperate_forest": ("Cfb", "Oceanic", "Mild and evenly wet with cool summers; deciduous/mixed forest."),
    "taiga": ("Dfc", "Subarctic boreal", "Long cold winters, short cool summers — coniferous taiga."),
    "tundra": ("ET", "Tundra", "Warmest month 0–10 °C over permafrost; treeless."),
    "snow": ("EF", "Ice cap", "Perennial frost — the warmest month stays below 0 °C."),
    "bare": ("H", "Alpine highland", "Climate governed by altitude: cold, thin air, bare rock."),
    "wetland": ("Cfa", "Humid subtropical wetland", "Waterlogged warm lowlands with very high humidity."),
    "beach": ("Cfb", "Maritime coast", "Sea-moderated — mild, humid, low seasonal range."),
}


def _koppen(distribution, cfg=None):
    """Assign a representative Köppen–Geiger climate class from the biome mix."""
    land = {d["biome"]: d["pct"] for d in distribution
            if d["biome"] not in ("ocean", "shallow", "lake", "river")}
    if not land:
        return {"code": "EF", "name": "Ice cap", "summary": "Open water / permanent ice; no land climate.",
                "dominant_biome": None}
    dom = max(land, key=land.get)
    code, name, summary = _KOPPEN_TABLE.get(dom, ("Cfb", "Temperate", "Moderate temperatures and rainfall."))
    return {"code": code, "name": name, "summary": summary, "dominant_biome": dom}


# ── biodiversity (Shannon–Wiener) ────────────────────────────────────────
def _shannon(distribution):
    land = [d["pct"] / 100.0 for d in distribution
            if d["biome"] not in ("ocean", "shallow", "lake", "river") and d["pct"] > 0]
    s = sum(land)
    if s <= 0 or not land:
        return {"index": 0.0, "evenness": 0.0, "richness": 0, "rating": "barren"}
    ps = [p / s for p in land]
    H = -sum(p * math.log(p) for p in ps)
    rich = len(ps)
    even = round(H / math.log(rich), 3) if rich > 1 else 0.0
    rating = ("rich" if H > 1.6 else "moderate" if H > 1.0 else "low" if H > 0.5 else "sparse")
    return {"index": round(H, 3), "evenness": even, "richness": rich, "rating": rating}


# ── 2. Plate tectonics & boundaries ──────────────────────────────────────
_TECTONIC_SETTINGS = [
    "intraplate (passive interior)", "divergent (continental rifting)",
    "convergent (oceanic subduction)", "transform (shear margin)",
    "convergent (continental collision)", "hotspot (mantle plume)",
]


def plate_points(n, seed, k=None):
    """Deterministic Voronoi seed-points for tectonic plates."""
    k = k or (3 + int(_h01(1, 1, seed) * 5))
    return [(int(_h01(100 + i, 7, seed) * n), int(_h01(7, 100 + i, seed) * n)) for i in range(k)]


def plate_at(x, y, pts):
    best, bd = 0, 1e18
    for i, (px, py) in enumerate(pts):
        d = (px - x) ** 2 + (py - y) ** 2
        if d < bd:
            bd, best = d, i
    return best


_BOUNDARY_TYPES = ["convergent", "divergent", "transform"]


def boundary_type(a, b, seed):
    return _BOUNDARY_TYPES[int(_h01(min(a, b) + 1, max(a, b) + 1, seed) * 3) % 3]


def _plates(n, peak, seed):
    """Voronoi plate model: per-plate geometry + boundary classification driving
    seismic & volcanic potential from real plate-boundary physics."""
    from collections import Counter
    pts = plate_points(n, seed)
    k = len(pts)
    pairs = [(a, b) for a in range(k) for b in range(a + 1, k)]
    bc = Counter(boundary_type(a, b, seed) for a, b in pairs)
    conv, div, trans = bc.get("convergent", 0), bc.get("divergent", 0), bc.get("transform", 0)
    tot = max(1, len(pairs))
    active = (conv + div) > 0
    boundary_density = round(min(1.0, peak * 0.6 + (conv + div + trans) / tot * 0.6), 2)
    seismic = min(3, int(round(boundary_density * 3)) if (conv + trans) > 0 else 1)
    volcanic = min(3, int(round((conv + div) / tot * (0.6 + peak) * 4)))
    primary = ("convergent (subduction/collision)" if conv >= max(div, trans)
               else "divergent (rifting)" if div >= trans else "transform (shear margin)")
    return {"plates": k, "primary_setting": primary, "boundary_density": boundary_density,
            "boundary_breakdown": {"convergent": conv, "divergent": div, "transform": trans},
            "active_margin": active, "seismic_potential": seismic, "volcanic_potential": volcanic,
            "note": f"{k} major plates with {conv} convergent, {div} divergent, {trans} transform "
                    f"boundaries → {'high' if seismic >= 2 else 'low'} seismicity, "
                    f"{'active' if volcanic >= 2 else 'minimal'} volcanism."}


# ── natural hazards (now plate-driven) ───────────────────────────────────
def _hazards(distribution, stats, seed, tectonics=None):
    pct = {d["biome"]: d["pct"] for d in distribution}
    peak = stats["peak_elevation"]; water = stats["water_pct"]
    arid = pct.get("desert", 0) + pct.get("savanna", 0) + pct.get("bare", 0)
    forest = pct.get("temperate_forest", 0) + pct.get("tropical_forest", 0) + pct.get("taiga", 0)
    jit = _h01(7, 13, seed) * 0.5
    clamp = lambda v: max(0, min(3, int(round(v))))
    tect_seis = tectonics["seismic_potential"] if tectonics else 0
    tect_volc = tectonics["volcanic_potential"] if tectonics else clamp(peak * 2.0)
    ratings = {
        "seismic": clamp(max(peak * 2.4 + jit, tect_seis)),         # plate boundaries dominate
        "volcanic": tect_volc,                                       # purely plate/hotspot driven
        "flood": clamp(water * 0.04 + pct.get("wetland", 0) * 0.12),
        "drought": clamp(arid * 0.035),
        "wildfire": clamp(forest * 0.028 + arid * 0.012),
    }
    levels = ["none", "low", "moderate", "high"]
    overall = levels[clamp(max(ratings.values()))]
    return {"levels": levels, "overall": overall,
            "ratings": {k: {"score": v, "label": levels[v]} for k, v in ratings.items()}}


# ── 3. Insolation / axial tilt / seasons ─────────────────────────────────
def _insolation(distribution, cfg, seed):
    tilt = round(15.0 + _h01(3, 3, seed) * 25.0, 1)                 # axial tilt 15–40°
    cold = sum(d["pct"] for d in distribution if d["biome"] in ("snow", "tundra", "taiga"))
    hot = sum(d["pct"] for d in distribution if d["biome"] in ("desert", "savanna", "tropical_forest"))
    mean_temp = round(14.0 + (hot - cold) * 0.18, 1)
    seasonal_range = round(8.0 + tilt * 0.7 + cold * 0.08, 1)
    day_len = round(22.0 + _h01(4, 4, seed) * 6.0, 1)              # sidereal day length, hours
    return {"axial_tilt_deg": tilt, "mean_annual_temp_c": mean_temp,
            "seasonal_range_c": seasonal_range, "day_length_h": day_len,
            "note": f"A {tilt}° axial tilt drives a ±{round(seasonal_range / 2, 1)} °C seasonal swing; "
                    f"mean annual surface temperature ≈ {mean_temp} °C."}


# ── 4. Atmospheric circulation & prevailing winds ────────────────────────
_WIND_BELTS = ["trade winds (easterlies)", "mid-latitude westerlies",
               "polar easterlies", "monsoonal seasonal reversal"]


def _winds(seed, insolation):
    belt = _WIND_BELTS[int(_h01(5, 5, seed) * len(_WIND_BELTS)) % len(_WIND_BELTS)]
    return {"prevailing": belt,
            "rain_shadow": "windward ranges wet; leeward basins arid",
            "note": f"Hadley/Ferrel circulation gives dominant {belt}; orographic uplift "
                    f"concentrates precipitation on windward slopes, drying the lee."}


# ── 5. Ocean surface currents (gyres) ────────────────────────────────────
def _currents(stats, seed):
    if stats["water_pct"] < 8:
        return {"regime": "endorheic / minimal open water",
                "note": "Too little open water for a basin-scale gyre; drainage is largely internal."}
    spin = "clockwise gyre (northern-hemisphere style)" if _h01(6, 6, seed) > 0.5 \
        else "anticlockwise gyre (southern-hemisphere style)"
    return {"regime": spin,
            "note": f"A wind-driven {spin} redistributes heat, moderating coastal temperatures "
                    f"and seeding upwelling fisheries on the eastern margin."}


# ── 6. Hydrology & Strahler stream order ─────────────────────────────────
def _hydrology(stats, rivers, peak):
    rt = stats.get("river_tiles", 0); lakes = stats.get("lakes", 0)
    strahler = min(6, 1 + rt // 40)
    discharge = round(rt * (0.5 + peak) * 12.0)                    # order-of-magnitude m³/s
    watersheds = max(1, lakes + strahler)
    return {"watersheds": watersheds, "max_strahler_order": strahler,
            "est_peak_discharge_m3s": discharge, "river_tiles": rt, "lakes": lakes,
            "note": f"Drainage organises into ~{watersheds} watersheds; trunk rivers reach "
                    f"Strahler order {strahler} with an estimated peak discharge ~{discharge:,} m³/s."}


# ── 7. Lithology / rock provinces ────────────────────────────────────────
def _lithology(plates, distribution, seed):
    setting = plates["primary_setting"]
    if "convergent" in setting:
        prov = ["andesitic arc volcanics", "folded sedimentary belts", "metamorphic basement"]
    elif "divergent" in setting:
        prov = ["basaltic flood provinces", "young rift sediments"]
    elif "hotspot" in setting:
        prov = ["ocean-island basalts", "tuff & scoria cones"]
    elif "transform" in setting:
        prov = ["sheared mélange", "uplifted cratonic blocks"]
    else:
        prov = ["cratonic shield (granite-gneiss)", "platform sedimentary cover"]
    return {"provinces": prov, "dominant": prov[0],
            "note": f"{setting.split()[0].title()} tectonics yields {prov[0]} as the dominant lithology."}


# ── 8. Economic geology / mineral & energy resources ─────────────────────
def _resources(lithology, plates, distribution):
    d = lithology["dominant"]; res = []
    if "basalt" in d or "volcanic" in d:
        res += ["copper porphyry", "geothermal energy"]
    if "sedimentary" in d or "platform" in d:
        res += ["hydrocarbons", "limestone", "coal"]
    if "metamorphic" in d or "shield" in d or "gneiss" in d:
        res += ["gold", "iron ore", "rare-earth elements"]
    if plates["primary_setting"].startswith("convergent"):
        res += ["polymetallic vein systems"]
    arable = sum(x["pct"] for x in distribution
                 if x["biome"] in ("grassland", "savanna", "temperate_forest"))
    if arable > 25:
        res += ["prime arable land"]
    return {"deposits": sorted(set(res)) or ["construction aggregate"], "arable_pct": round(arable, 1)}


# ── 9. Pedology / soil fertility ─────────────────────────────────────────
_SOIL_FERT = {"grassland": 0.9, "savanna": 0.7, "temperate_forest": 0.8, "wetland": 0.85,
              "tropical_forest": 0.5, "taiga": 0.4, "shrubland": 0.45, "tundra": 0.2,
              "desert": 0.1, "bare": 0.05, "snow": 0.0, "beach": 0.2}


def _soil(distribution, lithology):
    fert = 0.0
    for d in distribution:
        fert += (d["pct"] / 100.0) * _SOIL_FERT.get(d["biome"], 0.3)
    fert = round(min(1.0, fert * 1.4), 2)
    klass = ("fertile (mollisol/alfisol)" if fert > 0.6
             else "moderate (inceptisol)" if fert > 0.35
             else "poor (aridisol/gelisol)")
    return {"fertility_index": fert, "soil_class": klass,
            "note": f"Weathering of {lithology['dominant']} produces {klass} soils "
                    f"(fertility index {fert})."}


# ── 10. Carrying-capacity demographics ───────────────────────────────────
def _population(distribution, stats, pois, soil):
    arable = sum(x["pct"] for x in distribution
                 if x["biome"] in ("grassland", "savanna", "temperate_forest", "wetland"))
    cc = 5000.0 * (0.3 + soil["fertility_index"]) * (0.5 + arable / 100.0)
    total = int(len(pois) * cc + arable * 1500)
    density = round(total / max(1, stats["tiles"]), 1)
    return {"estimated_total": total, "density_per_tile": density,
            "note": f"Carrying capacity set by {round(arable, 1)}% arable land and soil fertility "
                    f"{soil['fertility_index']} → ≈ {total:,} inhabitants ({density}/tile)."}


# ── least-cost trade-route network ───────────────────────────────────────
def _tile_cost(b, e):
    if b == "ocean":
        return 12.0
    if b in ("lake", "river", "shallow"):
        return 4.5
    if b == "bare":
        return 3.0 + e * 5.0
    if b in ("snow", "tundra"):
        return 2.6
    if b == "desert":
        return 2.1
    if b in ("temperate_forest", "taiga", "tropical_forest"):
        return 1.6
    return 1.0


def _astar(grid, elev, start, goal, n):
    import heapq
    sx, sy = start; gx, gy = goal
    openq = [(0.0, 0.0, sx, sy)]
    came = {}; best = {(sx, sy): 0.0}
    while openq:
        _, g, x, y = heapq.heappop(openq)
        if (x, y) == (gx, gy):
            path = [(x, y)]
            while (x, y) in came:
                x, y = came[(x, y)]; path.append((x, y))
            return path[::-1], g
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            nx, ny = x + dx, y + dy
            if not (0 <= nx < n and 0 <= ny < n):
                continue
            ng = g + _tile_cost(grid[ny][nx]["b"], elev[ny][nx])
            if ng < best.get((nx, ny), 1e18):
                best[(nx, ny)] = ng
                came[(nx, ny)] = (x, y)
                heapq.heappush(openq, (ng + abs(nx - gx) + abs(ny - gy), ng, nx, ny))
    return None, float("inf")


def _trade_routes(grid, elev, pois, n):
    sites = [(p["x"], p["y"], p.get("name", ""), p.get("kind", "")) for p in pois][:14]
    if len(sites) < 2:
        return []
    edges, seen = [], set()
    for i, (x, y, nm, _k) in enumerate(sites):
        nbrs = sorted(range(len(sites)), key=lambda j: (sites[j][0] - x) ** 2 + (sites[j][1] - y) ** 2)
        for j in nbrs[1:3]:
            key = tuple(sorted((i, j)))
            if key in seen:
                continue
            seen.add(key)
            path, cost = _astar(grid, elev, (x, y), (sites[j][0], sites[j][1]), n)
            if path and cost < 1e17:
                edges.append({"from": sites[i][2], "to": sites[j][2],
                              "from_xy": [x, y], "to_xy": [sites[j][0], sites[j][1]],
                              "path": [[px, py] for px, py in path],
                              "cost": round(cost, 1), "tiles": len(path)})
    edges.sort(key=lambda e: e["cost"])
    return edges[:16]


# ── primary economy per settlement type ──────────────────────────────────
_ECONOMY = {
    "capital": "administration & regional trade", "city": "manufacturing, services & trade",
    "town": "markets, crafts & administration", "village": "subsistence & smallholder farming",
    "farmstead": "arable & livestock agriculture", "harbor": "shipping, fishing & maritime trade",
    "fishing_village": "coastal fishing & processing", "lighthouse": "navigation & coastal safety",
    "mine": "metal-ore & mineral extraction", "quarry": "stone & aggregate extraction",
    "logging_camp": "timber & forestry", "observatory": "astronomy & atmospheric research",
    "research_station": "scientific fieldwork & monitoring", "weather_station": "meteorological observation",
    "ghost_town": "abandoned (former extraction/agriculture)", "cave_system": "speleology & geotourism",
    "basecamp": "expedition logistics & survey",
}


def compute_systems(world, cfg, seed):
    """Assemble the full hyper-realism Earth-systems stack for a built world (20 models)."""
    dist = world["distribution"]; s = world["stats"]
    n = world["size"]; peak = s["peak_elevation"]
    pois = world.get("pois", []); routes = world.get("routes", [])
    tect = _plates(n, peak, seed)
    insol = _insolation(dist, cfg, seed)
    winds = _winds(seed, insol)
    currents = _currents(s, seed)
    hydro = _hydrology(s, world.get("rivers", []), peak)
    litho = _lithology(tect, dist, seed)
    resources = _resources(litho, tect, dist)
    soil = _soil(dist, litho)
    pop = _population(dist, s, pois, soil)
    # ── steps 11–20 ──
    magneto = _magnetosphere(seed, insol)
    atmos = _atmosphere(dist, tect, magneto, seed)
    productivity = _productivity(dist, insol)
    energy = _energy_balance(dist, insol)
    tides = _tides(seed)
    phenology = _phenology(insol, dist)
    hierarchy = _settlement_hierarchy(pois, pop)
    network = _network_metrics(routes, pois)
    economy = _macro_economy(resources, pop, hierarchy)
    habitability = _habitability(insol, atmos, energy, s, magneto)
    # ── steps 21–30 ──
    orbital = _orbital(seed)
    cryosphere = _cryosphere(dist, insol, seed)
    renewables = _renewables(dist, winds, insol, seed)
    agriculture = _agriculture(dist, soil, phenology)
    air_quality = _air_quality(tect, dist)
    coastal = _coastal(s, tides, seed)
    wildlife = _wildlife_corridors(dist, routes)
    astronomy = _astronomy(pois, dist, magneto, seed)
    water_security = _water_security(s, pop, hydro)
    risk_index = _risk_index(tect, s, dist, habitability)
    return {"tectonics": tect, "insolation": insol, "winds": winds, "currents": currents,
            "hydrology": hydro, "lithology": litho, "resources": resources, "soil": soil,
            "population": pop, "magnetosphere": magneto, "atmosphere": atmos,
            "productivity": productivity, "energy_balance": energy, "tides": tides,
            "phenology": phenology, "settlement_hierarchy": hierarchy, "network": network,
            "macro_economy": economy, "habitability": habitability,
            "orbital": orbital, "cryosphere": cryosphere, "renewables": renewables,
            "agriculture": agriculture, "air_quality": air_quality, "coastal": coastal,
            "wildlife_corridors": wildlife, "astronomy": astronomy,
            "water_security": water_security, "risk_index": risk_index}


# ── 21. Orbital mechanics & Milankovitch forcing ─────────────────────────
def _orbital(seed):
    ecc = round(_h01(21, 21, seed) * 0.18, 3)                    # eccentricity 0–0.18
    period = round(280 + _h01(22, 22, seed) * 600, 0)           # orbital period (days)
    severity = "strong" if ecc > 0.08 else "mild"
    return {"eccentricity": ecc, "orbital_period_days": period,
            "milankovitch_forcing": severity,
            "note": f"Orbital eccentricity {ecc} over a {period:.0f}-day year drives {severity} "
                    f"Milankovitch climate cycles (long-term glacial–interglacial swings)."}


# ── 22. Cryosphere — glaciation & sea level ──────────────────────────────
def _cryosphere(distribution, insolation, seed):
    ice = sum(d["pct"] for d in distribution if d["biome"] in ("snow", "tundra"))
    sea_level_trend = round((insolation["mean_annual_temp_c"] - 14) * 0.04 - ice * 0.01, 2)
    extent = "extensive ice sheets" if ice > 25 else "alpine/seasonal ice" if ice > 8 else "near ice-free"
    return {"ice_cover_pct": round(ice, 1), "extent": extent, "sea_level_trend_m_century": sea_level_trend,
            "note": f"{round(ice, 1)}% perennial/seasonal ice ({extent}); sea level trending "
                    f"{sea_level_trend:+} m/century with current forcing."}


# ── 23. Renewable-energy potential ───────────────────────────────────────
def _renewables(distribution, winds, insolation, seed):
    solar = round(min(1.0, 0.4 + (insolation["mean_annual_temp_c"]) / 40.0 + _h01(23, 23, seed) * 0.2), 2)
    wind = round(min(1.0, 0.4 + _h01(24, 24, seed) * 0.5), 2)
    hydro = round(min(1.0, sum(d["pct"] for d in distribution if d["biome"] in ("river", "lake")) / 12.0), 2)
    best = max((("solar", solar), ("wind", wind), ("hydro", hydro)), key=lambda x: x[1])[0]
    return {"solar_index": solar, "wind_index": wind, "hydro_index": hydro, "lead_source": best,
            "note": f"Renewable mix favours {best} (solar {solar}, wind {wind}, hydro {hydro})."}


# ── 24. Agricultural suitability ─────────────────────────────────────────
def _agriculture(distribution, soil, phenology):
    arable = sum(d["pct"] for d in distribution if d["biome"] in ("grassland", "savanna", "temperate_forest", "wetland"))
    score = round(min(1.0, (arable / 100.0) * 0.6 + soil["fertility_index"] * 0.3
                      + (phenology["growing_season_days"] / 365.0) * 0.1), 2)
    crops = []
    if phenology["growing_season_days"] > 300:
        crops += ["rice", "sugarcane"]
    if score > 0.4:
        crops += ["wheat", "maize", "legumes"]
    crops = crops or ["hardy roots & grazing"]
    return {"suitability_index": score, "primary_crops": crops, "arable_pct": round(arable, 1),
            "note": f"Agricultural suitability {score}; viable crops: {', '.join(crops)}."}


# ── 25. Air quality / volcanic aerosols ──────────────────────────────────
def _air_quality(tect, distribution):
    aerosol = tect["volcanic_potential"]
    dust = sum(d["pct"] for d in distribution if d["biome"] in ("desert", "bare")) * 0.01
    aqi = min(3, int(round(aerosol * 0.8 + dust)))
    labels = ["pristine", "good", "moderate", "hazy/volcanic"]
    return {"index": aqi, "label": labels[aqi],
            "note": f"Background air quality is {labels[aqi]} — driven by volcanic aerosol load "
                    f"and wind-blown dust."}


# ── 26. Coastal dynamics — erosion & sediment ────────────────────────────
def _coastal(stats, tides, seed):
    coast = stats["water_pct"]
    erosion = round(min(1.0, tides["mean_tidal_range_m"] / 8.0 + _h01(26, 26, seed) * 0.3), 2)
    deltas = int(stats.get("river_tiles", 0) / 30)
    return {"erosion_index": erosion, "delta_count_est": deltas, "tidal_range_m": tides["mean_tidal_range_m"],
            "note": f"Coastal erosion index {erosion} with ~{deltas} river-delta systems building "
                    f"sediment where trunk rivers meet the sea."}


# ── 27. Wildlife connectivity corridors ──────────────────────────────────
def _wildlife_corridors(distribution, routes):
    habitat = sum(d["pct"] for d in distribution
                  if d["biome"] in ("temperate_forest", "tropical_forest", "taiga", "grassland", "savanna", "wetland"))
    fragmentation = round(min(1.0, len(routes) / 18.0), 2)
    connectivity = round(max(0.0, habitat / 100.0 - fragmentation * 0.3), 2)
    return {"habitat_pct": round(habitat, 1), "connectivity_index": connectivity,
            "fragmentation": fragmentation,
            "note": f"{round(habitat, 1)}% contiguous habitat gives a wildlife-connectivity index of "
                    f"{connectivity} (human transport fragmentation {fragmentation})."}


# ── 28. Astronomical visibility (Bortle / dark skies) ────────────────────
def _astronomy(pois, distribution, magneto, seed):
    settlements = len([p for p in pois if p.get("kind") in ("city", "town", "capital", "harbor")])
    bortle = max(1, min(9, 2 + settlements // 2))
    obs = any(p.get("kind") == "observatory" for p in pois)
    return {"bortle_class": bortle, "dark_skies": bortle <= 3, "has_observatory": obs,
            "aurora": magneto.get("aurora"),
            "note": f"Bortle class {bortle} skies ({'excellent dark-sky sites' if bortle <= 3 else 'light-polluted near cities'})"
                    + ("; an observatory exploits the clear high-altitude air." if obs else ".")}


# ── 29. Water security ───────────────────────────────────────────────────
def _water_security(stats, population, hydrology):
    renew = stats["water_pct"] + hydrology["river_tiles"] * 0.05
    per_capita = round(renew * 1e6 / max(1, population["estimated_total"]), 1)
    stress = "abundant" if per_capita > 50 else "adequate" if per_capita > 15 else "stressed" if per_capita > 5 else "scarce"
    return {"renewable_water_index": round(renew, 1), "per_capita_proxy": per_capita, "stress_level": stress,
            "note": f"Freshwater availability is {stress} (per-capita proxy {per_capita})."}


# ── 30. Composite disaster-risk index ────────────────────────────────────
def _risk_index(tect, stats, distribution, habitability):
    seis = tect["seismic_potential"]; volc = tect["volcanic_potential"]
    flood = min(3, int(stats["water_pct"] * 0.04 + sum(d["pct"] for d in distribution if d["biome"] == "wetland") * 0.1))
    composite = round((seis + volc + flood) / 9.0 * (1.2 - habitability["index"] / 200.0), 2)
    band = "extreme" if composite > 0.66 else "high" if composite > 0.4 else "moderate" if composite > 0.2 else "low"
    return {"composite": composite, "band": band, "seismic": seis, "volcanic": volc, "flood": flood,
            "note": f"Composite multi-hazard disaster risk is {band} ({composite}) — combining seismic, "
                    f"volcanic and flood exposure against habitability."}


# ── 11. Magnetosphere & radiation environment ────────────────────────────
def _magnetosphere(seed, insolation):
    dynamo = round(0.2 + _h01(11, 11, seed) * 1.4, 2)            # dipole moment (Earth=1)
    spin = insolation["day_length_h"]
    strong = dynamo > 0.6 and spin < 30
    return {"dipole_moment_earths": dynamo, "field_strength": "strong" if strong else "weak",
            "surface_radiation": "shielded (Earth-like)" if strong else "elevated (thin shield)",
            "aurora": "vivid polar aurorae" if strong else "faint, low-latitude glow",
            "note": f"A core dynamo of {dynamo}× Earth's gives a {'protective' if strong else 'leaky'} "
                    f"magnetosphere, deflecting most stellar wind from the surface."}


# ── 12. Atmospheric composition & pressure ───────────────────────────────
def _atmosphere(distribution, tect, magneto, seed):
    veg = sum(d["pct"] for d in distribution
              if d["biome"] in ("temperate_forest", "tropical_forest", "taiga", "grassland", "savanna"))
    o2 = round(14.0 + veg * 0.12, 1)                              # % O2 from photosynthesis
    co2 = round(0.02 + tect["volcanic_potential"] * 0.14 + _h01(12, 12, seed) * 0.05, 3)
    pressure = round(0.7 + _h01(13, 13, seed) * 0.7, 2)          # bar (Earth=1.0)
    breathable = 16.0 <= o2 <= 23.0 and 0.7 <= pressure <= 1.3 and magneto["field_strength"] == "strong"
    return {"o2_pct": o2, "co2_pct": co2, "surface_pressure_bar": pressure,
            "breathable": breathable, "primary_gases": "N₂/O₂" if o2 > 12 else "CO₂/N₂",
            "note": f"~{o2}% O₂, {co2}% CO₂ at {pressure} bar — "
                    f"{'breathable for humans' if breathable else 'requires life support'}."}


# ── 13. Net primary productivity (carbon cycle) ──────────────────────────
def _productivity(distribution, insolation):
    npp_w = {"tropical_forest": 2200, "temperate_forest": 1250, "wetland": 2000, "savanna": 900,
             "grassland": 600, "taiga": 380, "shrubland": 260, "tundra": 140, "desert": 90,
             "bare": 10, "snow": 0, "beach": 60}
    npp = sum((d["pct"] / 100.0) * npp_w.get(d["biome"], 200) for d in distribution)
    npp = round(npp * (0.7 + insolation["mean_annual_temp_c"] / 60.0), 0)
    cls = "highly productive" if npp > 1000 else "moderately productive" if npp > 400 else "low productivity"
    return {"npp_g_m2_yr": npp, "class": cls,
            "note": f"Mean net primary productivity ≈ {npp:,} g C/m²/yr ({cls}) — sets the food web's ceiling."}


# ── 14. Planetary energy balance & albedo ────────────────────────────────
def _energy_balance(distribution, insolation):
    alb = {"snow": 0.8, "tundra": 0.5, "desert": 0.4, "bare": 0.35, "beach": 0.3, "ocean": 0.08,
           "shallow": 0.1, "lake": 0.08, "river": 0.08, "grassland": 0.2, "savanna": 0.22,
           "shrubland": 0.24, "temperate_forest": 0.15, "tropical_forest": 0.13, "taiga": 0.12,
           "wetland": 0.14}
    albedo = round(sum((d["pct"] / 100.0) * alb.get(d["biome"], 0.2) for d in distribution), 3)
    eq_temp = round(insolation["mean_annual_temp_c"] - albedo * 18.0, 1)
    return {"bond_albedo": albedo, "equilibrium_temp_c": eq_temp,
            "note": f"A Bond albedo of {albedo} reflects sunlight to an equilibrium "
                    f"temperature near {eq_temp} °C before greenhouse forcing."}


# ── 15. Moons & tides ────────────────────────────────────────────────────
def _tides(seed):
    moons = int(_h01(14, 14, seed) * 3.99)                       # 0–3 moons
    rng = round(0.2 + moons * (0.8 + _h01(15, 15, seed) * 2.5), 1) if moons else round(0.1 + _h01(15, 15, seed) * 0.4, 1)
    return {"moons": moons, "mean_tidal_range_m": rng,
            "note": f"{moons} moon(s) raise a mean tidal range of ~{rng} m, "
                    f"{'driving strong intertidal ecosystems' if rng > 2 else 'with modest coastal mixing'}."}


# ── 16. Phenology / growing season ───────────────────────────────────────
def _phenology(insolation, distribution):
    base = 365 - insolation["seasonal_range_c"] * 6.5
    cold = sum(d["pct"] for d in distribution if d["biome"] in ("snow", "tundra", "taiga"))
    season = int(max(30, min(365, base - cold * 1.2)))
    return {"growing_season_days": season,
            "harvests_per_year": 1 if season < 200 else 2 if season < 320 else 3,
            "note": f"A {season}-day growing season permits "
                    f"{1 if season < 200 else 2 if season < 320 else 3} harvest(s) per year."}


# ── 17. Settlement hierarchy (rank-size / Zipf) ──────────────────────────
def _settlement_hierarchy(pois, pop):
    ranks = {"capital": 5, "city": 4, "harbor": 4, "town": 3, "village": 2, "farmstead": 1}
    tiers = sorted((ranks.get(p.get("kind"), 1) for p in pois), reverse=True)
    primacy = round(tiers[0] / tiers[1], 2) if len(tiers) > 1 and tiers[1] else 1.0
    return {"levels": len(set(tiers)), "primacy_index": primacy, "settlements": len(pois),
            "follows_zipf": len(tiers) >= 4,
            "note": f"{len(pois)} settlements across {len(set(tiers))} tiers; primacy index {primacy} "
                    f"({'primate (one dominant centre)' if primacy >= 2 else 'balanced rank-size'})."}


# ── 18. Transport-network metrics ────────────────────────────────────────
def _network_metrics(routes, pois):
    nodes = min(len(pois), 14); edges = len(routes)
    density = round(edges / max(1, nodes), 2)
    connected = edges >= nodes - 1
    longest = max((r.get("tiles", 0) for r in routes), default=0)
    return {"nodes": nodes, "corridors": edges, "edge_density": density,
            "connected": connected, "longest_corridor_tiles": longest,
            "note": f"{edges} corridors link {nodes} hubs (density {density}); the network is "
                    f"{'fully connected' if connected else 'fragmented'}."}


# ── 19. Macro-economy (resource + demographic proxy) ─────────────────────
def _macro_economy(resources, population, hierarchy):
    pop = population["estimated_total"]
    base = 1800 + len(resources.get("deposits", [])) * 900 + hierarchy["levels"] * 600
    gdp = int(pop * base / 1000)
    sectors = []
    if resources.get("arable_pct", 0) > 25:
        sectors.append("agriculture")
    if any("ore" in d or "gold" in d or "copper" in d for d in resources.get("deposits", [])):
        sectors.append("mining")
    if any("hydrocarbon" in d or "geothermal" in d for d in resources.get("deposits", [])):
        sectors.append("energy")
    sectors = sectors or ["subsistence"]
    return {"est_gdp_proxy": gdp, "gdp_per_capita": int(base), "lead_sectors": sectors,
            "note": f"An economy of ≈ {gdp:,} (proxy units) led by {', '.join(sectors)}."}


# ── 20. Composite habitability index (0–100) ─────────────────────────────
def _habitability(insolation, atmosphere, energy, stats, magneto):
    score = 100.0
    t = insolation["mean_annual_temp_c"]
    score -= min(40, abs(t - 14) * 1.8)                          # comfort band ~14 °C
    if not atmosphere["breathable"]:
        score -= 28
    if magneto["field_strength"] != "strong":
        score -= 12
    if stats["water_pct"] < 8 or stats["water_pct"] > 92:
        score -= 14
    score -= max(0, (abs(energy["equilibrium_temp_c"]) - 30) * 0.6)
    score = int(max(0, min(100, score)))
    band = ("Earth-like" if score >= 80 else "habitable" if score >= 60
            else "marginal" if score >= 40 else "hostile" if score >= 20 else "lethal")
    return {"index": score, "class": band,
            "note": f"Composite habitability {score}/100 — {band}: weighs temperature, breathable "
                    f"air, magnetic shielding, water budget and energy balance."}
