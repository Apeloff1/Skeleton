"""
🌌 WORLDFORGE CORE — pure procedural world-generation engine (split from worldforge.py, 2026-06).

Constants/catalogs (biomes, palettes, climates, structures, cosmic objects, scales),
the WorldConfig model, and the deterministic build pipeline (region/planet/cosmic).
No FastAPI, no DB — pure, seedable, byte-identical generation. Imported by
routes/worldforge.py (routes + PIL render) and routes/worldforge_publish.py.
"""
from __future__ import annotations

import re
import math
import random
from collections import Counter

from pydantic import BaseModel

MAX_SIZE = 96
SEA_LEVEL = 0.30

# ── planetary biomes (16) ──
BIOMES = {
    "ocean": {"color": "#1d4ed8", "emoji": "🌊", "label": "Ocean"},
    "shallow": {"color": "#3b82f6", "emoji": "💧", "label": "Shallow Sea"},
    "lake": {"color": "#38bdf8", "emoji": "🏞️", "label": "Lake"},
    "river": {"color": "#22d3ee", "emoji": "🏞️", "label": "River"},
    "beach": {"color": "#fcd34d", "emoji": "🏖️", "label": "Beach"},
    "desert": {"color": "#f59e0b", "emoji": "🏜️", "label": "Desert"},
    "savanna": {"color": "#d9c44a", "emoji": "🌾", "label": "Savanna"},
    "grassland": {"color": "#84cc16", "emoji": "🟩", "label": "Grassland"},
    "shrubland": {"color": "#65a30d", "emoji": "🌿", "label": "Shrubland"},
    "wetland": {"color": "#4d7c0f", "emoji": "🪷", "label": "Wetland"},
    "tropical_forest": {"color": "#15803d", "emoji": "🌴", "label": "Tropical Forest"},
    "temperate_forest": {"color": "#16a34a", "emoji": "🌳", "label": "Temperate Forest"},
    "taiga": {"color": "#0f766e", "emoji": "🌲", "label": "Taiga"},
    "tundra": {"color": "#94a3b8", "emoji": "🍂", "label": "Tundra"},
    "bare": {"color": "#a8a29e", "emoji": "⛰️", "label": "Bare Rock"},
    "snow": {"color": "#f1f5f9", "emoji": "❄️", "label": "Snow"},
}
WATER = {"ocean", "shallow", "lake", "river"}

# ── palette themes: per-biome colour overrides (default 'natural' = base) ──
PALETTES = {
    "natural": {},
    "verdant": {"grassland": "#3fbf3f", "temperate_forest": "#0f9d58", "savanna": "#a3d44a"},
    "arid": {"grassland": "#c2a23f", "temperate_forest": "#8a9a3f", "savanna": "#e0b84a",
             "shrubland": "#9a8a3f", "beach": "#f0d68a"},
    "frozen": {"grassland": "#cfe8ee", "temperate_forest": "#9fc6cf", "taiga": "#6f97a0",
               "desert": "#e7eef0", "savanna": "#d6e6ea", "bare": "#cfd8dc"},
    "volcanic": {"grassland": "#5a3a2a", "temperate_forest": "#3a2a22", "bare": "#3a1f1a",
                 "desert": "#7a3a1a", "beach": "#5a3320", "snow": "#7a2a1a"},
    "alien": {"grassland": "#a64ce0", "temperate_forest": "#7a2cb0", "ocean": "#1a8a8a",
              "shallow": "#26c6c6", "desert": "#c46be0", "savanna": "#b86bd0"},
    "toxic": {"grassland": "#9acd32", "ocean": "#3a7a2a", "shallow": "#5aa83a",
              "temperate_forest": "#6a8a1a", "lake": "#7ab83a"},
    "oceanic": {"ocean": "#0c5fb0", "shallow": "#2b8fd6", "beach": "#ffe39a"},
    "ashen": {"grassland": "#6a6a5a", "temperate_forest": "#4a4a40", "bare": "#3a3a36",
              "desert": "#7a7060", "snow": "#9a9a92"},
    "twilight": {"grassland": "#3a4a8a", "temperate_forest": "#2a2a6a", "ocean": "#0a0a3a",
                 "shallow": "#1a2a6a", "snow": "#c0c8f0", "desert": "#6a5a9a"},
}

# ── climate presets: bias the moisture/temperature/sea fields ──
CLIMATES = {
    "temperate": {"moist": 0.0, "temp": 0.0, "sea": 0.0},
    "arid": {"moist": -0.28, "temp": 0.15, "sea": -0.03},
    "tropical": {"moist": 0.22, "temp": 0.28, "sea": 0.01},
    "frozen": {"moist": -0.05, "temp": -0.42, "sea": -0.02},
    "oceanic": {"moist": 0.16, "temp": 0.04, "sea": 0.09},
    "volcanic": {"moist": -0.12, "temp": 0.34, "sea": -0.04},
    "swamp": {"moist": 0.38, "temp": 0.12, "sea": 0.03},
    "alpine": {"moist": 0.05, "temp": -0.2, "sea": -0.08},
    "alien": {"moist": 0.1, "temp": 0.1, "sea": -0.01},
}

# ── structure / settlement kinds (toggleable features) ──
# Realism doctrine: ONLY real human-geography settlement & infrastructure types,
# sited by genuine locating logic (water access, arable lowland, ore-bearing
# uplands, defensible ridges, clear high-altitude skies for observatories, etc.).
# No castles/dungeons/temples/shrines/monoliths or other fantasy tropes.
STRUCTURES = {
    "city": {"icon": "🏙️", "label": "City", "biomes": {"grassland", "shrubland", "temperate_forest"}, "elev": (0.38, 0.6)},
    "town": {"icon": "🏘️", "label": "Town", "biomes": {"grassland", "shrubland", "savanna", "temperate_forest"}, "elev": (0.37, 0.7)},
    "village": {"icon": "🛖", "label": "Village", "biomes": {"grassland", "savanna", "wetland", "shrubland"}, "elev": (0.37, 0.68)},
    "farmstead": {"icon": "🌾", "label": "Farmstead", "biomes": {"grassland", "savanna", "shrubland"}, "elev": (0.38, 0.62)},
    "harbor": {"icon": "⚓", "label": "Harbor", "biomes": {"beach"}, "elev": (0.36, 0.42)},
    "fishing_village": {"icon": "🎣", "label": "Fishing Village", "biomes": {"beach"}, "elev": (0.36, 0.43)},
    "lighthouse": {"icon": "🗼", "label": "Lighthouse", "biomes": {"beach", "bare"}, "elev": (0.4, 0.72)},
    "mine": {"icon": "⛏️", "label": "Mine", "biomes": {"bare", "tundra", "desert"}, "elev": (0.55, 0.9)},
    "quarry": {"icon": "🪨", "label": "Quarry", "biomes": {"bare", "desert", "savanna"}, "elev": (0.45, 0.85)},
    "logging_camp": {"icon": "🪵", "label": "Logging Camp", "biomes": {"taiga", "temperate_forest", "tropical_forest"}, "elev": (0.4, 0.78)},
    "observatory": {"icon": "🔭", "label": "Observatory", "biomes": {"bare", "snow", "tundra", "desert"}, "elev": (0.7, 0.96)},
    "research_station": {"icon": "🛰️", "label": "Research Station", "biomes": {"tundra", "snow", "desert", "bare"}, "elev": (0.45, 0.92)},
    "weather_station": {"icon": "🌡️", "label": "Weather Station", "biomes": {"tundra", "bare", "snow", "shrubland"}, "elev": (0.5, 0.9)},
    "ghost_town": {"icon": "🏚️", "label": "Ghost Town", "biomes": {"desert", "savanna", "tundra", "bare"}, "elev": (0.37, 0.8)},
    "cave_system": {"icon": "🕳️", "label": "Cave System", "biomes": {"bare", "temperate_forest", "taiga"}, "elev": (0.6, 0.88)},
    "basecamp": {"icon": "⛺", "label": "Basecamp", "biomes": {"taiga", "tundra", "shrubland", "grassland"}, "elev": (0.4, 0.82)},
}

# ── cosmic-scale object palettes ──
COSMIC = {
    "system": {
        "space": {"color": "#05060f", "label": "Deep Space", "emoji": "🌑"},
        "star": {"color": "#fde047", "label": "Star", "emoji": "⭐"},
        "corona": {"color": "#fb923c", "label": "Corona", "emoji": "🔥"},
        "rocky": {"color": "#a8a29e", "label": "Rocky Planet", "emoji": "🪨"},
        "ocean_world": {"color": "#2563eb", "label": "Ocean World", "emoji": "🌍"},
        "gas_giant": {"color": "#d97706", "label": "Gas Giant", "emoji": "🪐"},
        "ice_world": {"color": "#bae6fd", "label": "Ice World", "emoji": "🧊"},
        "asteroid": {"color": "#57534e", "label": "Asteroid", "emoji": "☄️"},
        "comet": {"color": "#93c5fd", "label": "Comet", "emoji": "💫"},
    },
    "galaxy": {
        "void": {"color": "#04040c", "label": "Void", "emoji": "⬛"},
        "dust": {"color": "#1b1230", "label": "Dust Lane", "emoji": "🌫️"},
        "nebula": {"color": "#7c3aed", "label": "Nebula", "emoji": "🌌"},
        "star_dim": {"color": "#64748b", "label": "Dim Star", "emoji": "·"},
        "star": {"color": "#e2e8f0", "label": "Star", "emoji": "⭐"},
        "star_hot": {"color": "#93c5fd", "label": "Blue Giant", "emoji": "🔵"},
        "core": {"color": "#fde68a", "label": "Galactic Core", "emoji": "🌟"},
    },
    "cosmos": {
        "void": {"color": "#020208", "label": "Cosmic Void", "emoji": "⬛"},
        "filament": {"color": "#1e1b4b", "label": "Filament", "emoji": "🕸️"},
        "nebula": {"color": "#9333ea", "label": "Nebula", "emoji": "🌌"},
        "spiral": {"color": "#38bdf8", "label": "Spiral Galaxy", "emoji": "🌀"},
        "elliptical": {"color": "#fbbf24", "label": "Elliptical Galaxy", "emoji": "🟡"},
        "cluster": {"color": "#f472b6", "label": "Galaxy Cluster", "emoji": "✨"},
        "quasar": {"color": "#f8fafc", "label": "Quasar", "emoji": "💠"},
    },
}

SCALES = [
    {"id": "region", "label": "Region", "emoji": "🗺️", "desc": "Detailed terrain you can walk."},
    {"id": "planet", "label": "Planet", "emoji": "🌍", "desc": "A whole world with polar ice caps."},
    {"id": "system", "label": "Star System", "emoji": "🪐", "desc": "A star and its orbiting worlds."},
    {"id": "galaxy", "label": "Galaxy", "emoji": "🌌", "desc": "Spiral arms, nebulae and a blazing core."},
    {"id": "cosmos", "label": "Cosmos", "emoji": "🌠", "desc": "The cosmic web of galaxies and clusters."},
]

# Naming + noise primitives live in dedicated leaf modules (Session 13c refactor).
from .worldforge_noise import _h01, _smooth, _vnoise, _fbm, _ridged  # noqa: F401
from .worldforge_naming import _name, _astro_name, _explain_toponym  # noqa: F401
from .worldforge_render import (  # render primitives (split out)
    _shade_hex, _hue_of, _grid_arrays, _bilinear, _starfield,
    _cfont, _lerp_cmap, _fbm_field,
)


# ════════════════════════════════════════════════════════════════════════
#  WORLD CONFIG
# ════════════════════════════════════════════════════════════════════════
class WorldConfig(BaseModel):
    scale: str = "region"
    seed: int = 1337
    size: int = 48
    rx: int = 0
    ry: int = 0
    noise_scale: float = 0.08
    palette: str = "natural"
    climate: str = "temperate"
    sea_level: float = 0.30
    mountain_level: float = 0.72
    snow_level: float = 0.85
    moisture_bias: float = 0.0
    temperature_bias: float = 0.0
    warp_strength: float = 1.6
    ridge_strength: float = 0.45
    octaves: int = 5
    erosion: float = 0.0
    river_density: float = 0.04
    lake_density: float = 0.6
    settlement_density: float = 1.0
    # structure toggles (defaults preserve the classic settlement set)
    features: dict = {}
    # cosmic knobs
    star_density: float = 0.05
    nebula: float = 0.5
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0

    def clamp(self):
        self.size = max(8, min(int(self.size), MAX_SIZE))
        self.noise_scale = max(0.02, min(float(self.noise_scale), 0.5))
        self.octaves = max(2, min(int(self.octaves), 7))
        if self.scale not in {s["id"] for s in SCALES}:
            self.scale = "region"
        if self.palette not in PALETTES:
            self.palette = "natural"
        if self.climate not in CLIMATES:
            self.climate = "temperate"
        return self


def _palette_color(biome, palette):
    return PALETTES.get(palette, {}).get(biome) or BIOMES[biome]["color"]


def _elevation(gx, gy, seed, cfg):
    ws = cfg.warp_strength
    # fractal (two-level) domain warping — Quilez-style — for organic, non-grid coastlines
    q1 = _fbm(gx + 5.2, gy + 1.3, seed ^ 0x51ED, 4)
    q2 = _fbm(gx + 9.1, gy + 7.7, seed ^ 0x2A11, 4)
    wx = _fbm(gx + 4.0 * q1 + 1.7, gy + 4.0 * q2 + 9.2, seed ^ 0x51ED, 3)
    wy = _fbm(gx + 4.0 * q1 + 8.3, gy + 4.0 * q2 + 2.8, seed ^ 0x2A11, 3)
    px, py = gx + (wx - 0.5) * ws, gy + (wy - 0.5) * ws
    # layered fBm — continental shelf (low freq) + regional relief + fine detail
    cont = _fbm(px * 0.5, py * 0.5, seed, max(3, cfg.octaves))
    regional = _fbm(px, py, seed ^ 0x1234, cfg.octaves)
    detail = (_fbm(px * 2.2, py * 2.2, seed ^ 0x99, 3) - 0.5) * 0.35
    base = cont * 0.55 + regional * 0.45 + detail
    base = 0.5 + (base - 0.5) * 1.85          # restore variance lost to layer averaging
    # tectonic ridges concentrated on continental margins (ridged multifractal)
    ridge = _ridged(px, py, seed ^ 0x7777, 5)
    mask = max(0.0, (base - 0.45)) * 2.0
    rs = cfg.ridge_strength
    e = base * (1 - rs * mask) + ridge * (rs * mask)
    e = 0.0 if e < 0.0 else 1.0 if e > 1.0 else e
    return e ** 1.08


def _hydraulic_erode(elev, n, seed, droplets, steps=24):
    """Droplet-based hydraulic erosion — carves valleys, river channels & talus,
    depositing sediment in basins. Deterministic (seeded). Mutates elev in place."""
    import random
    rnd = random.Random((seed ^ 0xE0DE) & 0xFFFFFFFF)
    er, dep, evap, cap = 0.22, 0.10, 0.02, 3.6
    for _ in range(droplets):
        x = rnd.uniform(1, n - 2); y = rnd.uniform(1, n - 2)
        dx = dy = sed = 0.0; water = 1.0; speed = 1.0
        for _ in range(steps):
            ix, iy = int(x), int(y)
            if not (1 <= ix < n - 1 and 1 <= iy < n - 1):
                break
            gxv = elev[iy][ix + 1] - elev[iy][ix - 1]
            gyv = elev[iy + 1][ix] - elev[iy - 1][ix]
            dx = dx * 0.8 - gxv; dy = dy * 0.8 - gyv
            ln = (dx * dx + dy * dy) ** 0.5
            if ln < 1e-6:
                break
            dx /= ln; dy /= ln
            nx, ny = x + dx, y + dy
            inx, iny = int(nx), int(ny)
            if not (0 <= inx < n and 0 <= iny < n):
                break
            dh = elev[iny][inx] - elev[iy][ix]
            c = max(0.0, -dh) * speed * water * cap
            if dh > 0 or sed > c:
                drop = min(sed, dh) if dh > 0 else (sed - c) * dep
                elev[iy][ix] += drop; sed -= drop
            else:
                take = min((c - sed) * er, 0.05)
                elev[iy][ix] -= take; sed += take
            speed = (max(0.0, speed * speed - dh)) ** 0.5
            water *= (1 - evap)
            x, y = nx, ny
    for yy in range(n):
        for xx in range(n):
            v = elev[yy][xx]
            elev[yy][xx] = 0.0 if v < 0.0 else 1.0 if v > 1.0 else v


def _classify(elev, moist, temp, cfg):
    sl, ml, snl = cfg.sea_level, cfg.mountain_level, cfg.snow_level
    if elev < sl:
        return "ocean"
    if elev < sl + 0.04:
        return "shallow"
    if elev < sl + 0.07:
        return "beach"
    if elev > snl:
        return "snow" if temp < 0.5 else "bare"
    if elev > ml:
        if temp < 0.35:
            return "snow"
        if moist < 0.35:
            return "bare"
        return "tundra" if temp < 0.5 else "taiga"
    if temp < 0.30:
        return "tundra" if moist < 0.4 else "taiga"
    if temp < 0.55:
        if moist < 0.30:
            return "grassland"
        if moist < 0.60:
            return "shrubland"
        if moist > 0.85 and elev < 0.45:
            return "wetland"
        return "temperate_forest"
    if moist < 0.25:
        return "desert"
    if moist < 0.45:
        return "savanna"
    if moist > 0.85 and elev < 0.45:
        return "wetland"
    if moist < 0.70:
        return "grassland"
    return "tropical_forest"


def _shade(eg, x, y, n):
    xl = eg[y][x - 1] if x > 0 else eg[y][x]
    xr = eg[y][x + 1] if x < n - 1 else eg[y][x]
    yu = eg[y - 1][x] if y > 0 else eg[y][x]
    yd = eg[y + 1][x] if y < n - 1 else eg[y][x]
    return max(0.6, min(1.35, 1.0 + ((xr - xl) + (yd - yu)) * 6.0))


# ════════════════════════════════════════════════════════════════════════
#  PLANETARY BUILDER (region + planet)
# ════════════════════════════════════════════════════════════════════════
def _default_features(cfg) -> dict:
    """Resolve which structure kinds are active for this build."""
    f = dict(cfg.features or {})
    # classic settlement set is on unless explicitly disabled
    for k in ("town", "village", "harbor", "farmstead"):
        f.setdefault(k, True)
    return f


def _build_planet(cfg: WorldConfig, planet: bool = False) -> dict:
    n, sc = cfg.size, cfg.noise_scale
    seed = cfg.seed
    ms, ts = seed ^ 0x9E3779B9, seed ^ 0x85EBCA77
    ox, oy = cfg.rx * n, cfg.ry * n
    cl = CLIMATES[cfg.climate]
    mbias = cfg.moisture_bias + cl["moist"]
    tbias = cfg.temperature_bias + cl["temp"]
    cfg.sea_level = max(0.1, min(0.6, cfg.sea_level + cl["sea"]))

    elev = [[0.0] * n for _ in range(n)]
    moist = [[0.0] * n for _ in range(n)]
    temp = [[0.0] * n for _ in range(n)]
    for y in range(n):
        for x in range(n):
            gx, gy = (ox + x + cfg.pan_x) * sc, (oy + y + cfg.pan_y) * sc
            e = _elevation(gx, gy, seed, cfg)
            m = max(0.0, min(1.0, _fbm(gx + 100, gy + 100, ms, 4) + mbias))
            # planet scale: strong latitude band gives polar ice + equatorial heat
            if planet:
                lat = abs(y / max(1, n - 1) - 0.5) * 2
            else:
                lat = abs(((oy + y) % 512) / 512.0 - 0.5) * 2
            t = _fbm(gx + 200, gy + 200, ts, 3) * 0.5 + (1 - lat) * 0.5 - e * 0.4 + tbias
            elev[y][x], moist[y][x], temp[y][x] = e, m, max(0.0, min(1.0, t))

    # AAA hydraulic erosion: droplet sim carves valleys, ridgelines & river channels
    _hydraulic_erode(elev, n, cfg.seed, droplets=int(n * n * (0.22 + cfg.erosion * 0.5)))
    # optional thermal smoothing pass on top of the carved relief
    for _ in range(int(round(cfg.erosion * 2))):
        ne = [[elev[y][x] for x in range(n)] for y in range(n)]
        for y in range(n):
            for x in range(n):
                acc = cnt = 0
                for dy in (-1, 0, 1):
                    for dx in (-1, 0, 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < n and 0 <= ny < n:
                            acc += elev[ny][nx]; cnt += 1
                ne[y][x] = acc / cnt
        elev = ne

    # hydrology — steepest-descent flow accumulation
    NB = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
    land = [(elev[y][x], x, y) for y in range(n) for x in range(n) if elev[y][x] >= cfg.sea_level]
    land.sort(reverse=True)
    flow = [[1.0] * n for _ in range(n)]
    is_lake = [[False] * n for _ in range(n)]
    for e, x, y in land:
        lowest, le = None, e
        for dx, dy in NB:
            nx, ny = x + dx, y + dy
            if 0 <= nx < n and 0 <= ny < n and elev[ny][nx] < le:
                le, lowest = elev[ny][nx], (nx, ny)
        if lowest is None:
            if flow[y][x] > n * cfg.lake_density and elev[y][x] < 0.7:
                is_lake[y][x] = True
        else:
            flow[lowest[1]][lowest[0]] += flow[y][x]
    lf = sorted((flow[y][x] for _e, x, y in land), reverse=True)
    rthr = max(8.0, n * 1.4)
    if lf and cfg.river_density > 0:
        idx = max(1, int(len(lf) * cfg.river_density))
        rthr = max(8.0, min(rthr, lf[min(idx, len(lf) - 1)]))
    elif cfg.river_density <= 0:
        rthr = 1e9  # rivers off

    grid, counts, rivers = [], Counter(), []
    for y in range(n):
        row = []
        for x in range(n):
            e, m, t = elev[y][x], moist[y][x], temp[y][x]
            b = _classify(e, m, t, cfg)
            if b not in WATER:
                if is_lake[y][x]:
                    b = "lake"
                elif flow[y][x] >= rthr and cfg.sea_level <= e < 0.8:
                    b = "river"
                    if len(rivers) < 1500:
                        rivers.append([x, y])
            counts[b] += 1
            base = _palette_color(b, cfg.palette)
            color = base if b in WATER else _shade_hex(base, _shade(elev, x, y, n))
            row.append({"b": b, "c": color, "e": round(e, 3), "m": round(m, 3), "t": round(t, 3)})
        grid.append(row)

    pois = _place_structures(grid, elev, flow, is_lake, cfg, ox, oy, n)
    total = n * n
    distribution = [
        {"biome": b, "label": BIOMES[b]["label"], "emoji": BIOMES[b]["emoji"],
         "color": _palette_color(b, cfg.palette), "count": c, "pct": round(100 * c / total, 1)}
        for b, c in counts.most_common()
    ]
    wt = sum(counts.get(b, 0) for b in WATER)
    peak = max(max(r) for r in elev)
    koppen = _koppen(distribution, cfg)
    routes = _trade_routes(grid, elev, pois, n)
    biodiversity = _shannon(distribution)
    for p in pois:
        p["economy"] = _ECONOMY.get(p["kind"], "mixed local economy")
    base_stats = {"tiles": total, "biomes": len(counts),
                  "land_pct": round(100 * (total - wt) / total, 1),
                  "water_pct": round(100 * wt / total, 1),
                  "river_tiles": counts.get("river", 0), "lakes": counts.get("lake", 0),
                  "settlements": len(pois), "peak_elevation": round(peak, 3),
                  "koppen": koppen["code"], "trade_routes": len(routes),
                  "biodiversity": biodiversity["index"]}
    world_partial = {"size": n, "distribution": distribution, "stats": base_stats,
                     "rivers": rivers, "pois": pois}
    systems = compute_systems(world_partial, cfg, seed)
    hazards = _hazards(distribution, base_stats, seed, tectonics=systems["tectonics"])
    base_stats["hazard"] = hazards["overall"]
    base_stats["population"] = systems["population"]["estimated_total"]
    return {
        "scale": "planet" if planet else "region", "seed": seed, "size": n,
        "region": {"x": cfg.rx, "y": cfg.ry}, "scale_freq": sc, "name": _name(seed, cfg.rx, cfg.ry),
        "palette": cfg.palette, "climate": cfg.climate,
        "grid": grid, "distribution": distribution, "rivers": rivers, "pois": pois,
        "koppen": koppen, "routes": routes, "biodiversity": biodiversity, "hazards": hazards,
        "systems": systems, "stats": base_stats,
    }



# Earth-systems models (Köppen, plate tectonics, insolation, winds, currents,
# hydrology, lithology, resources, soil, demographics, biodiversity, hazards,
# trade routes, economy) live in the dedicated worldforge_systems module.
from .worldforge_systems import (  # noqa: F401
    _koppen, _shannon, _hazards, _trade_routes, _tile_cost, _astar,
    _ECONOMY, _KOPPEN_TABLE, _SOIL_FERT, compute_systems,
    plate_points, plate_at, boundary_type,
)


def _place_structures(grid, elev, flow, is_lake, cfg, ox, oy, n):
    feats = _default_features(cfg)
    active = [k for k, on in feats.items() if on and k in STRUCTURES]
    if not active:
        active = ["village"]
    NB = [(-1, -1), (0, -1), (1, -1), (-1, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]

    def near_water(x, y):
        for dx, dy in NB:
            nx, ny = x + dx, y + dy
            if 0 <= nx < n and 0 <= ny < n and grid[ny][nx]["b"] in ("river", "lake", "shallow"):
                return True
        return False

    cands = []  # (score, x, y, kind)
    for y in range(n):
        for x in range(n):
            b = grid[y][x]["b"]
            e = elev[y][x]
            for kind in active:
                spec = STRUCTURES[kind]
                if b not in spec["biomes"]:
                    continue
                lo, hi = spec["elev"]
                if not (lo <= e <= hi):
                    continue
                slope = _shade(elev, x, y, n)
                flat = 1.0 - abs(slope - 1.0)
                water = 0.5 if near_water(x, y) else 0.0
                jitter = _h01(ox + x, oy + y, cfg.seed ^ (hash(kind) & 0xFFFF))
                pri = {"city": 1.5, "town": 1.2, "village": 1.1, "harbor": 1.1,
                       "fishing_village": 1.0, "lighthouse": 1.0, "farmstead": 0.95,
                       "mine": 0.9, "logging_camp": 0.9, "observatory": 0.9,
                       "research_station": 0.9, "quarry": 0.85, "weather_station": 0.85,
                       "cave_system": 0.85, "ghost_town": 0.8, "basecamp": 0.8}.get(kind, 0.9)
                score = (flat * 0.7 + water + jitter * 0.6) * pri
                cands.append((score, x, y, kind))
    cands.sort(reverse=True)

    target = max(3, int((n // 8) * 2 * cfg.settlement_density))
    gap = max(2, n // 12)
    pois, used = [], []
    capital_done = False
    for score, x, y, kind in cands:
        if len(pois) >= target:
            break
        if any(abs(x - px) < gap and abs(y - py) < gap for px, py in used):
            continue
        if kind in ("city", "town", "village") and not capital_done:
            kind2, icon, capital_done = "capital", "🏛️", True
        else:
            kind2, icon = kind, STRUCTURES[kind]["icon"]
        pois.append({"x": x, "y": y, "kind": kind2, "icon": icon,
                     "name": _name(cfg.seed ^ (x * 31 + y), x, y,
                                   biome=grid[y][x]["b"], kind=kind2)})
        used.append((x, y))
    return pois


# ════════════════════════════════════════════════════════════════════════
#  COSMIC BUILDERS (system / galaxy / cosmos)
# ════════════════════════════════════════════════════════════════════════
def _build_cosmic(cfg: WorldConfig) -> dict:
    n, seed, kind = cfg.size, cfg.seed, cfg.scale
    pal = COSMIC[kind]
    ox, oy = cfg.rx * n, cfg.ry * n
    cx, cy = n / 2, n / 2
    grid, counts, pois = [], Counter(), []
    sc = cfg.noise_scale * (1.6 if kind == "cosmos" else 1.2)
    for y in range(n):
        row = []
        for x in range(n):
            gx, gy = (ox + x) * sc, (oy + y) * sc
            dx, dy = x - cx, y - cy
            dist = math.hypot(dx, dy) / (n / 2)
            ang = math.atan2(dy, dx)
            field = _fbm(gx + 11, gy + 7, seed, 4)
            empty = "space" if kind == "system" else "void"
            obj = empty
            if kind == "system":
                ring = (_fbm(gx, gy, seed ^ 9, 2))
                if dist < 0.10:
                    obj = "star"
                elif dist < 0.16:
                    obj = "corona"
                else:
                    # planets sit on faint orbital bands
                    band = abs(math.sin(dist * 14.0)) 
                    if band > 0.86 and _h01(ox + x, oy + y, seed) > 0.55:
                        r = _h01(ox + x, oy + y, seed ^ 5)
                        obj = ("gas_giant" if r > 0.8 else "ice_world" if r > 0.62
                               else "ocean_world" if r > 0.42 else "rocky")
                    elif field > 0.78 and ring > 0.7:
                        obj = "asteroid"
                    elif field > 0.9:
                        obj = "comet"
            elif kind == "galaxy":
                # logarithmic spiral arms
                arm = math.sin(ang * 2 - dist * 7.0 + seed * 0.001)
                density = (1 - dist) * 0.7 + arm * 0.4 + (field - 0.5) * 0.5
                if dist < 0.06:
                    obj = "core"
                elif density > 0.62:
                    r = _h01(ox + x, oy + y, seed ^ 3)
                    obj = "star_hot" if r > 0.9 else "star" if r > 0.45 else "star_dim"
                elif _fbm(gx + 50, gy + 50, seed ^ 22, 3) > 0.7 and density > 0.3:
                    obj = "nebula"
                elif density > 0.42:
                    obj = "dust"
            else:  # cosmos — the cosmic web
                web = _fbm(gx, gy, seed, 5)
                fil = abs(_fbm(gx + 30, gy + 30, seed ^ 7, 4) - 0.5)
                if web > 0.80:
                    r = _h01(ox + x, oy + y, seed ^ 2)
                    obj = ("quasar" if r > 0.96 else "cluster" if r > 0.8
                           else "elliptical" if r > 0.5 else "spiral")
                elif web > 0.62 and _fbm(gx + 60, gy + 60, seed ^ 13, 3) > 0.66:
                    obj = "nebula"
                elif fil < 0.10:
                    obj = "filament"
            counts[obj] += 1
            row.append({"b": obj, "c": pal[obj]["color"]})
        grid.append(row)

    # name notable objects as POIs
    notable = {"system": {"gas_giant", "ocean_world", "ice_world", "rocky", "star"},
               "galaxy": {"core", "star_hot", "nebula"},
               "cosmos": {"quasar", "cluster", "elliptical", "spiral", "nebula"}}[kind]
    for y in range(n):
        for x in range(n):
            if len(pois) >= max(4, n // 6):
                break
            b = grid[y][x]["b"]
            if b in notable and _h01(ox + x, oy + y, seed ^ 0xC0) > 0.86:
                if not any(abs(x - px) < n // 10 and abs(y - py) < n // 10 for px, py in [(p["x"], p["y"]) for p in pois]):
                    pois.append({"x": x, "y": y, "kind": b, "icon": pal[b]["emoji"],
                                 "name": _name(seed ^ (x * 17 + y), x, y, space=True, kind=b)})
    total = n * n
    distribution = [
        {"biome": b, "label": pal[b]["label"], "emoji": pal[b]["emoji"],
         "color": pal[b]["color"], "count": c, "pct": round(100 * c / total, 1)}
        for b, c in counts.most_common()
    ]
    occupied = total - counts.get("space" if kind == "system" else "void", 0)
    empty_ct = counts.get("space" if kind == "system" else "void", 0)
    return {
        "scale": kind, "seed": seed, "size": n, "region": {"x": cfg.rx, "y": cfg.ry},
        "scale_freq": sc, "name": _name(seed, cfg.rx, cfg.ry, space=True, kind=kind),
        "palette": cfg.palette, "climate": cfg.climate,
        "grid": grid, "distribution": distribution, "rivers": [], "pois": pois,
        "stats": {"tiles": total, "biomes": len(counts),
                  "land_pct": round(100 * occupied / total, 1),
                  "water_pct": round(100 * empty_ct / total, 1),
                  "river_tiles": 0, "lakes": 0,
                  "settlements": len(pois), "peak_elevation": round(max(0.0, 1 - 0), 3)},
    }


def build_world(cfg: WorldConfig) -> dict:
    cfg.clamp()
    if cfg.scale == "region":
        return _build_planet(cfg, planet=False)
    if cfg.scale == "planet":
        return _build_planet(cfg, planet=True)
    return _build_cosmic(cfg)
