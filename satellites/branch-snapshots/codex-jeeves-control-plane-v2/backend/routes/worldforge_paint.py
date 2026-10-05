"""
🪐 WORLDFORGE PAINT — numpy/PIL renderers (split from worldforge.py, 2026-06).

All the heavy PNG/GIF render functions: relief planes, Tolkien cartography, hyper-real
satellite atlas, cyan blueprint, supersampled globe (+ rotating GIF), thematic GIS
choropleths, tectonic-plate maps, NASA-style galaxies, and the branded export canvas.
Pure rendering — consumes a built world dict + WorldConfig from worldforge_core. Imported
by routes/worldforge.py (route handlers call these). No FastAPI here.
"""
from __future__ import annotations

import math

from .worldforge_core import (  # noqa: F401
    WorldConfig, build_world, _SOIL_FERT,
    plate_points, plate_at, boundary_type,
    _fbm, _grid_arrays, _bilinear, _starfield, _cfont, _lerp_cmap, _fbm_field,
    _shade_hex, _hue_of,
)

def _render_world(cfg: WorldConfig) -> bytes:
    import io
    import numpy as np
    from PIL import Image, ImageFilter
    world = build_world(cfg)
    rgb, elev, n = _grid_arrays(world)
    S = 768
    scale = cfg.scale

    if scale in ("region",):
        # ── premium relief plane: bicubic upscale + radial light + vignette ──
        img = Image.fromarray(rgb.astype(np.uint8)).resize((S, S), Image.BICUBIC)
        a = np.asarray(img, dtype=np.float64)
        yy, xx = np.mgrid[0:S, 0:S]
        cx = cy = S / 2
        r = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2) / (S / 2)
        light = np.clip(1.18 - r * 0.45, 0.55, 1.18)[..., None]
        vig = np.clip(1.05 - (r ** 2.4) * 0.55, 0.35, 1.05)[..., None]
        a = a * light * vig
        # soft bloom on bright/snow areas
        bloom = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(5))
        a = np.clip(a + np.asarray(bloom, dtype=np.float64) * 0.18, 0, 255)
        out = a.astype(np.uint8)

    elif scale == "planet":
        # ── GLOBE: orthographic sphere, Lambert + rim + specular + clouds + atmosphere ──
        bg = _starfield(S, cfg.seed, density=0.0010)
        yy, xx = np.mgrid[0:S, 0:S].astype(np.float64)
        cx = cy = S / 2; R = S * 0.43
        nx = (xx - cx) / R; ny = (yy - cy) / R
        r2 = nx * nx + ny * ny
        inside = r2 <= 1.0
        nz = np.sqrt(np.clip(1 - r2, 0, 1))
        # map visible front hemisphere → grid
        lon = np.arctan2(nx, np.maximum(nz, 1e-6)); lat = np.arcsin(np.clip(ny, -1, 1))
        gx = (lon / (math.pi / 2) * 0.5 + 0.5) * (n - 1)
        gy = (lat / (math.pi / 2) * 0.5 + 0.5) * (n - 1)
        surf = _bilinear(rgb, gx, gy, n)
        ev = _bilinear(elev, gx, gy, n)
        # Lambert from a sun in the upper-left-front
        sun = np.array([-0.55, -0.6, 0.58]); sun = sun / np.linalg.norm(sun)
        normal = np.stack([nx, ny, nz], axis=-1)
        lam = np.clip((normal * sun).sum(-1), 0, 1)
        shade = (0.18 + 0.82 * lam)[..., None]
        col = surf * shade
        # specular glint on oceans (low elevation)
        water = (ev < cfg.sea_level + 0.02)
        refl = np.clip((2 * nz * (normal * sun).sum(-1) - sun[2]), 0, 1)
        spec = (refl ** 28)[..., None] * 220 * water[..., None]
        col = col + spec
        # clouds (grid-space fbm so they wrap with rotation), lit by the sun
        cloud = np.zeros((n, n))
        for yi in range(n):
            for xi in range(n):
                cloud[yi, xi] = _fbm(xi * 0.12 + 7, yi * 0.12 + 3, cfg.seed ^ 0xC10D, 4)
        cl = _bilinear(cloud, gx, gy, n)
        cmask = np.clip((cl - 0.55) / 0.45, 0, 1) * 0.55
        col = col * (1 - cmask[..., None]) + np.array([245., 248., 255.]) * (cmask[..., None]) * shade
        # rim / atmosphere fresnel on the limb
        rim = ((1 - nz) ** 3)[..., None] * np.array([90., 150., 255.]) * 1.1
        col = col + rim
        col = np.where(inside[..., None], col, bg)
        # outer atmosphere halo
        rr = np.sqrt(r2)
        halo = np.exp(-np.clip(rr - 1.0, 0, 1) * 9.0) * (rr > 1.0)
        col = col + halo[..., None] * np.array([70., 130., 230.])
        out = np.clip(col, 0, 255).astype(np.uint8)

    else:
        # ── cosmic: soft glow field + bloom + starfield ──
        img = Image.fromarray(rgb.astype(np.uint8)).resize((S, S), Image.BILINEAR)
        base = np.asarray(img, dtype=np.float64)
        lum = base.mean(-1)
        bright = np.where(lum[..., None] > 60, base, 0).astype(np.uint8)
        bloom = Image.fromarray(bright).filter(ImageFilter.GaussianBlur(9))
        glow = np.asarray(bloom, dtype=np.float64) * 1.4
        stars = _starfield(S, cfg.seed ^ 0xA11, density=0.0022, bright=1.0)
        yy, xx = np.mgrid[0:S, 0:S]
        r = np.sqrt((xx - S / 2) ** 2 + (yy - S / 2) ** 2) / (S / 2)
        vig = np.clip(1.0 - (r ** 2.2) * 0.5, 0.25, 1.0)[..., None]
        out = np.clip((base + glow) * vig + stars, 0, 255).astype(np.uint8)

    buf = io.BytesIO()
    Image.fromarray(out).save(buf, format="PNG")
    return buf.getvalue()




def _render_world_hi(cfg: WorldConfig, mode: str = "auto") -> bytes:
    # crank detail for planetary scales (exquisite terrain)
    if cfg.scale in ("region", "planet"):
        cfg.size = max(cfg.size, 80)
        cfg.octaves = max(cfg.octaves, 6)
    world = build_world(cfg)
    if cfg.scale == "region":
        if mode == "atlas":
            return _render_atlas(world, cfg)
        if mode == "blueprint":
            return _render_blueprint(world, cfg)
        return _render_cartographic(world, cfg)
    if cfg.scale == "planet":
        return _render_globe(world, cfg)
    # galaxy / cosmos
    if mode == "bloom":
        return _render_cosmic_img(world, cfg)
    return _render_galaxy_nasa(world, cfg)


def _render_cartographic(world: dict, cfg: WorldConfig) -> bytes:
    """A hand-drawn TOLKIEN-style map: parchment, ink coastlines, hatched
    mountains, stippled forests, river ink-lines, named settlements, compass
    rose, double border + cartouche — supersampled ×2 then Lanczos-downscaled."""
    import io
    import numpy as np
    from PIL import Image, ImageDraw, ImageFilter
    rgb, elev, n = _grid_arrays(world)
    SS = 2; S = 768; W = S * SS
    eimg = Image.fromarray((elev * 255).astype(np.uint8)).resize((W, W), Image.BICUBIC)
    E = np.asarray(eimg, dtype=np.float64) / 255.0
    sea = cfg.sea_level
    land = E >= sea
    rng = np.random.default_rng(cfg.seed & 0x7FFFFFFF)
    pap = rng.normal(0, 1, (W, W))
    pap = (pap - pap.min()) / max(1e-6, (pap.max() - pap.min()))
    pap = np.asarray(Image.fromarray((pap * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(2)),
                     dtype=np.float64) / 255.0
    # land parchment + gentle sepia hillshade; ocean pale teal with depth bands
    gx, gy = np.gradient(E)
    sh = np.clip(1.0 + (gx + gy) * 6.5, 0.72, 1.22)[..., None]
    parch = np.array([234, 217, 172]) * (0.93 + 0.10 * pap[..., None])
    landcol = parch * sh
    depth = np.clip((sea - E) / max(sea, 1e-3), 0, 1)
    ocean = np.array([182, 206, 200]) * (1 - depth[..., None] * 0.45) + np.array([110, 142, 146]) * (depth[..., None] * 0.45)
    # faint bathymetric contour rings
    ring = (np.sin(depth * 26.0) > 0.85) & (~land)
    ocean[ring] *= 0.93
    arr = np.where(land[..., None], landcol, ocean)
    # ink coastline (edge of land mask, thickened)
    lm = Image.fromarray((land.astype(np.uint8) * 255))
    edge = np.asarray(lm.filter(ImageFilter.MaxFilter(3)), dtype=np.float64) - np.asarray(lm, dtype=np.float64)
    coast = edge > 40
    coast2 = np.asarray(Image.fromarray((coast.astype(np.uint8) * 255)).filter(ImageFilter.MaxFilter(3)), dtype=np.float64) > 40
    arr[coast2] = np.array([78, 56, 34])
    arr[coast] = np.array([54, 38, 22])
    im = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8))
    d = ImageDraw.Draw(im)
    cw = W / n
    ink = (74, 52, 30); forest = (44, 74, 46); blue = (70, 96, 150)
    # terrain glyphs
    g = world["grid"]
    for y in range(n):
        for x in range(n):
            t = g[y][x]; b = t["b"]; e = t.get("e", 0.5)
            cx, cy = x * cw + cw / 2, y * cw + cw / 2
            if b in ("bare", "snow") or e > cfg.mountain_level:
                w0 = max(1, int(SS))
                d.line([(cx - cw * 0.55, cy + cw * 0.35), (cx, cy - cw * 0.55)], fill=ink, width=w0)
                d.line([(cx, cy - cw * 0.55), (cx + cw * 0.55, cy + cw * 0.35)], fill=ink, width=w0)
                if b == "snow":
                    d.line([(cx - cw * 0.2, cy - cw * 0.1), (cx, cy - cw * 0.4)], fill=(150, 130, 110), width=1)
            elif b in ("temperate_forest", "tropical_forest", "taiga"):
                r = cw * 0.2
                d.ellipse([cx - r, cy - r - cw * 0.1, cx + r, cy + r - cw * 0.1], outline=forest, width=max(1, int(SS)))
                d.line([(cx, cy + r * 0.4), (cx, cy + r * 1.3)], fill=forest, width=max(1, int(SS)))
            elif b == "river":
                d.ellipse([cx - SS, cy - SS, cx + SS, cy + SS], fill=blue)
            elif b in ("desert", "savanna"):
                d.point([(cx, cy), (cx + cw * 0.3, cy + cw * 0.2)], fill=(150, 120, 70))
    # trade roads: dashed sepia least-cost routes between settlements (under the markers)
    for rt in world.get("routes", []):
        pts = [(px * cw + cw / 2, py * cw + cw / 2) for px, py in rt.get("path", [])]
        if len(pts) < 2:
            continue
        d.line(pts, fill=(198, 172, 122), width=max(2, int(SS * 1.6)), joint="curve")  # tan casing
        for i in range(0, len(pts) - 1):
            if i % 2 == 0:                                                              # dashed brown road
                d.line([pts[i], pts[i + 1]], fill=(122, 86, 46), width=max(1, int(SS)))
    # settlements: marker + serif-ish label
    flab = _cfont(int(15 * SS))
    for p in world["pois"][:16]:
        cx, cy = p["x"] * cw + cw / 2, p["y"] * cw + cw / 2
        if p["kind"] in ("capital", "city"):
            d.rectangle([cx - 5 * SS, cy - 5 * SS, cx + 5 * SS, cy + 5 * SS], fill=(150, 36, 24), outline=(40, 22, 12), width=SS)
        else:
            d.ellipse([cx - 4 * SS, cy - 4 * SS, cx + 4 * SS, cy + 4 * SS], fill=(120, 32, 20), outline=(40, 20, 10), width=SS)
        nm = p["name"]
        tx, ty = cx + 8 * SS, cy - 9 * SS
        for ox2, oy2 in ((-1, 0), (1, 0), (0, -1), (0, 1)):  # halo for legibility
            d.text((tx + ox2, ty + oy2), nm, fill=(232, 216, 172), font=flab)
        d.text((tx, ty), nm, fill=(52, 32, 18), font=flab)
    # decorative double border + cartouche + compass rose
    m = int(15 * SS)
    d.rectangle([m, m, W - m, W - m], outline=(70, 50, 30), width=int(3 * SS))
    d.rectangle([m + 7 * SS, m + 7 * SS, W - m - 7 * SS, W - m - 7 * SS], outline=(120, 92, 58), width=SS)
    tfont = _cfont(int(30 * SS))
    title = world["name"]
    d.rectangle([m + 14 * SS, m + 12 * SS, m + 14 * SS + int(d.textlength(title, font=tfont)) + 24 * SS, m + 12 * SS + 44 * SS],
                fill=(228, 210, 165), outline=(90, 66, 40), width=SS)
    d.text((m + 26 * SS, m + 18 * SS), title, fill=(60, 38, 20), font=tfont)
    # compass rose (bottom-right)
    ccx, ccy, rr = W - m - 52 * SS, W - m - 52 * SS, 30 * SS
    for ang, ln in ((0, 1.0), (90, 0.7), (180, 0.7), (270, 0.7)):
        import math as _m
        a = _m.radians(ang - 90)
        d.line([(ccx, ccy), (ccx + _m.cos(a) * rr * ln, ccy + _m.sin(a) * rr * ln)], fill=(80, 56, 32), width=int(2 * SS))
    d.ellipse([ccx - 4 * SS, ccy - 4 * SS, ccx + 4 * SS, ccy + 4 * SS], fill=(120, 90, 56))
    d.text((ccx - 4 * SS, ccy - rr - 16 * SS), "N", fill=(70, 48, 28), font=_cfont(int(16 * SS)))
    out = im.resize((S, S), Image.LANCZOS)
    buf = io.BytesIO(); out.save(buf, format="PNG"); return buf.getvalue()



# ── GIS THEMATIC ATLAS LAYERS — per-tile choropleth recolouring ──
_THEMATIC = {
    "elevation": ("Elevation", [(0, (40, 80, 140)), (0.32, (60, 140, 90)), (0.6, (185, 172, 95)),
                                 (0.8, (150, 110, 70)), (1, (248, 248, 252))]),
    "temperature": ("Temperature", [(0, (40, 70, 175)), (0.5, (236, 236, 180)), (1, (200, 50, 40))]),
    "moisture": ("Moisture", [(0, (200, 170, 110)), (0.5, (120, 182, 142)), (1, (40, 110, 152))]),
    "fertility": ("Soil fertility", [(0, (182, 150, 110)), (0.5, (162, 182, 92)), (1, (40, 120, 50))]),
    "seismic": ("Seismic risk", [(0, (70, 150, 90)), (0.5, (242, 212, 80)), (1, (200, 50, 40))]),
    "plates": ("Tectonic plates", None),
}
_PLATE_PALETTE = [(91, 143, 198), (224, 153, 92), (118, 184, 138), (198, 120, 168),
                  (148, 162, 196), (210, 196, 120), (120, 170, 180), (186, 138, 120)]


def _render_plates(world: dict, cfg: WorldConfig) -> bytes:
    """Tectonic-plate atlas layer: Voronoi plates with highlighted boundaries."""
    import io
    import numpy as np
    from PIL import Image, ImageDraw
    n = world["size"]
    pts = plate_points(n, cfg.seed)
    pid = [[plate_at(x, y, pts) for x in range(n)] for y in range(n)]
    arr = np.zeros((n, n, 3), dtype=np.uint8)
    for y in range(n):
        for x in range(n):
            me = pid[y][x]
            bnd = any(0 <= y + dy < n and 0 <= x + dx < n and pid[y + dy][x + dx] != me
                      for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            arr[y][x] = (38, 26, 30) if bnd else _PLATE_PALETTE[me % len(_PLATE_PALETTE)]
    S = 768
    im = Image.fromarray(arr).resize((S, S), Image.NEAREST)
    d = ImageDraw.Draw(im, "RGBA")
    f = _cfont(22); fs = _cfont(14)
    d.rectangle([0, 0, S, 42], fill=(12, 18, 28, 215))
    d.text((14, 10), f"Tectonic plates · {world['name']}", font=f, fill=(235, 240, 250))
    cw = S / n
    for i, (px, py) in enumerate(pts):
        cx, cy = int(px * cw + cw / 2), int(py * cw + cw / 2)
        d.ellipse([cx - 7, cy - 7, cx + 7, cy + 7], fill=(255, 255, 255), outline=(20, 20, 20))
        d.text((cx + 9, cy - 8), f"P{i + 1}", font=fs, fill=(255, 255, 255))
    buf = io.BytesIO(); im.save(buf, format="PNG"); return buf.getvalue()


def _render_thematic(world: dict, cfg: WorldConfig, layer: str) -> bytes:
    """A real-GIS choropleth: recolour every tile by a chosen scientific variable
    (elevation/temperature/moisture/soil fertility/seismic risk) with a legend."""
    import io
    import numpy as np
    from PIL import Image, ImageDraw
    g = world["grid"]; n = world["size"]
    layer = layer if layer in _THEMATIC else "elevation"
    title, stops = _THEMATIC[layer]
    if layer == "plates":
        return _render_plates(world, cfg)
    tect = world.get("systems", {}).get("tectonics", {})
    volc = tect.get("volcanic_potential", 0) / 3.0
    seis = tect.get("seismic_potential", 0) / 3.0
    water = {"ocean", "shallow", "lake", "river"}
    arr = np.zeros((n, n, 3), dtype=np.uint8)
    for y in range(n):
        for x in range(n):
            t = g[y][x]; b = t["b"]; e = t.get("e", 0.5); m = t.get("m", 0.5); tp = t.get("t", 0.5)
            if b in water and layer not in ("temperature", "moisture"):
                arr[y][x] = (150, 180, 192); continue
            if layer == "elevation":
                v = e
            elif layer == "temperature":
                v = tp
            elif layer == "moisture":
                v = m
            elif layer == "fertility":
                v = _SOIL_FERT.get(b, 0.3)
            else:  # seismic
                v = 0.0 if b in water else min(1.0, max(seis * 0.5, e * 0.6 + volc * 0.4))
            arr[y][x] = _lerp_cmap(v, stops)
    S = 768
    im = Image.fromarray(arr).resize((S, S), Image.NEAREST)
    d = ImageDraw.Draw(im, "RGBA")
    f = _cfont(22); fs = _cfont(14)
    d.rectangle([0, 0, S, 42], fill=(12, 18, 28, 215))
    d.text((14, 10), f"{title} · {world['name']}", font=f, fill=(235, 240, 250))
    lx, ly = S - 224, S - 46
    for i in range(200):
        d.line([(lx + i, ly), (lx + i, ly + 16)], fill=_lerp_cmap(i / 200.0, stops))
    d.rectangle([lx, ly, lx + 200, ly + 16], outline=(235, 235, 235))
    d.text((lx, ly - 18), "low", font=fs, fill=(235, 235, 235))
    d.text((lx + 174, ly - 18), "high", font=fs, fill=(235, 235, 235))
    buf = io.BytesIO(); im.save(buf, format="PNG"); return buf.getvalue()



def _render_globe(world: dict, cfg: WorldConfig, lon_offset: float = 0.0, out_size: int = 768) -> bytes:
    """Supersampled, exquisitely-shaded GLOBE (Lambert + rim + specular + detailed
    clouds + atmosphere + starfield). Renders ~1.5× then Lanczos-downscales."""
    import io
    import numpy as np
    from PIL import Image
    rgb, elev, n = _grid_arrays(world)
    S = int(out_size * 1.6)
    bg = _starfield(S, cfg.seed, density=0.0009)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float64)
    cx = cy = S / 2; R = S * 0.44
    nx = (xx - cx) / R; ny = (yy - cy) / R
    r2 = nx * nx + ny * ny
    inside = r2 <= 1.0
    nz = np.sqrt(np.clip(1 - r2, 0, 1))
    lon = np.arctan2(nx, np.maximum(nz, 1e-6)); lat = np.arcsin(np.clip(ny, -1, 1))
    gx = (lon / (math.pi / 2) * 0.5 + 0.5) * (n - 1) + lon_offset * n
    gx = np.mod(gx, n - 1)
    gy = (lat / (math.pi / 2) * 0.5 + 0.5) * (n - 1)
    surf = _bilinear(rgb, gx, gy, n)
    ev = _bilinear(elev, gx, gy, n)
    sun = np.array([-0.55, -0.6, 0.58]); sun = sun / np.linalg.norm(sun)
    normal = np.stack([nx, ny, nz], axis=-1)
    dot = (normal * sun).sum(-1)
    lam = np.clip(dot, 0, 1)
    shade = (0.16 + 0.84 * lam)[..., None] * (0.82 + 0.34 * ev[..., None])  # highlands catch light
    col = surf * shade
    water = (ev < cfg.sea_level + 0.02)
    refl = np.clip((2 * nz * dot - sun[2]), 0, 1)
    col = col + (refl ** 30)[..., None] * 235 * water[..., None]
    # day/night terminator: deepen the unlit hemisphere + warm twilight band
    night = np.clip(-dot, 0, 1)
    col = col * (1 - night[..., None] * 0.62)
    twi = np.exp(-((dot - 0.05) / 0.06) ** 2) * inside.astype(np.float64)
    col = col + twi[..., None] * np.array([72., 34., 14.])
    # two-layer clouds for depth
    cl1 = np.zeros((n, n)); cl2 = np.zeros((n, n))
    for yi in range(n):
        for xi in range(n):
            cl1[yi, xi] = _fbm(xi * 0.14 + 7, yi * 0.14 + 3, cfg.seed ^ 0xC10D, 5)
            cl2[yi, xi] = _fbm(xi * 0.30 + 19, yi * 0.30 + 5, cfg.seed ^ 0x5EED, 4)
    cl = _bilinear((cl1 * 0.6 + cl2 * 0.4), gx, gy, n)
    cmask = np.clip((cl - 0.54) / 0.46, 0, 1) * 0.6
    col = col * (1 - cmask[..., None]) + np.array([248., 250., 255.]) * cmask[..., None] * shade
    # polar ice caps — whiten high latitudes (sea-ice + glacier), lit by the sun
    icel = np.clip((np.abs(lat) - 1.04) / 0.46, 0, 1)
    col = col * (1 - icel[..., None] * 0.85) + np.array([236., 243., 252.]) * (icel[..., None] * 0.85) * shade
    rim = ((1 - nz) ** 3)[..., None] * np.array([95., 155., 255.]) * 1.15
    col = col + rim
    # faint graticule (meridians + parallels) → a cartographic globe feel
    grat = ((np.abs((lon * 6.0 / math.pi) % 1.0 - 0.5) < 0.016) |
            (np.abs((lat * 6.0 / math.pi) % 1.0 - 0.5) < 0.016))
    gmask = (grat & inside)[..., None]
    col = np.where(gmask, col * 0.62 + np.array([150., 195., 255.]) * 0.38, col)
    col = np.where(inside[..., None], col, bg)
    rr = np.sqrt(r2)
    halo = (np.exp(-np.clip(rr - 1.0, 0, 1) * 8.0) * (rr > 1.0))
    col = col + halo[..., None] * np.array([70., 130., 235.])
    out = Image.fromarray(np.clip(col, 0, 255).astype(np.uint8)).resize((out_size, out_size), Image.LANCZOS)
    buf = io.BytesIO(); out.save(buf, format="PNG"); return buf.getvalue()


def _render_cosmic_img(world: dict, cfg: WorldConfig) -> bytes:
    import io
    import numpy as np
    from PIL import Image, ImageFilter
    rgb, elev, n = _grid_arrays(world)
    S = 768; W = int(S * 1.5)
    img = Image.fromarray(rgb.astype(np.uint8)).resize((W, W), Image.BILINEAR)
    base = np.asarray(img, dtype=np.float64)
    lum = base.mean(-1)
    bright = np.where(lum[..., None] > 55, base, 0).astype(np.uint8)
    bloom = np.asarray(Image.fromarray(bright).filter(ImageFilter.GaussianBlur(11)), dtype=np.float64) * 1.5
    bloom2 = np.asarray(Image.fromarray(bright).filter(ImageFilter.GaussianBlur(4)), dtype=np.float64) * 0.9
    stars = _starfield(W, cfg.seed ^ 0xA11, density=0.0024)
    yy, xx = np.mgrid[0:W, 0:W]
    r = np.sqrt((xx - W / 2) ** 2 + (yy - W / 2) ** 2) / (W / 2)
    vig = np.clip(1.0 - (r ** 2.2) * 0.5, 0.22, 1.0)[..., None]
    out = np.clip((base + bloom + bloom2) * vig + stars, 0, 255).astype(np.uint8)
    res = Image.fromarray(out).resize((S, S), Image.LANCZOS)
    buf = io.BytesIO(); res.save(buf, format="PNG"); return buf.getvalue()


def _atlas_overlays(img, world: dict, cfg: WorldConfig):
    """Cartographic overlays on the satellite relief → a true NASA-hybrid map:
    faint graticule, contour-ish guide lines, settlement markers + labels with
    drop-shadow, a scale bar and a north arrow."""
    from PIL import ImageDraw
    W, H = img.size
    d = ImageDraw.Draw(img, "RGBA")
    n = max(1, world["size"])

    # elevation contour lines (faint cream) → topographic feel
    try:
        import numpy as np
        from PIL import Image as _PImg
        _rgb, _elev, _gn = _grid_arrays(world)
        Eh = np.asarray(_PImg.fromarray((_elev * 255).astype(np.uint8)).resize((W, H), _PImg.BICUBIC), dtype=np.float64) / 255.0
        lv = np.floor(Eh / 0.07)
        cedge = (np.abs(lv - np.roll(lv, 1, axis=1)) + np.abs(lv - np.roll(lv, 1, axis=0))) > 0
        cov = np.zeros((H, W, 4), dtype=np.uint8)
        cov[cedge] = (236, 230, 214, 64)
        ov = _PImg.fromarray(cov, "RGBA")
        img.paste(ov, (0, 0), ov)
    except Exception:
        pass

    def _lbl(xy, text, font, fill=(245, 247, 250, 240)):
        x, y = xy
        d.text((x + 1, y + 1), text, font=font, fill=(0, 0, 0, 190))
        d.text((x, y), text, font=font, fill=fill)

    # 8×8 graticule (real coordinate lattice)
    for i in range(1, 8):
        gx, gy = int(W * i / 8), int(H * i / 8)
        d.line([(gx, 0), (gx, H)], fill=(255, 255, 255, 26), width=1)
        d.line([(0, gy), (W, gy)], fill=(255, 255, 255, 26), width=1)

    # settlement markers sized by importance + labels
    fnt = _cfont(13)
    big = {"capital", "city", "fortress", "port"}
    for p in world.get("pois", [])[:20]:
        sx = int(p.get("x", 0) / n * W)
        sy = int(p.get("y", 0) / n * H)
        r = 5 if p.get("kind") in big else 3
        d.ellipse([sx - r, sy - r, sx + r, sy + r], fill=(255, 246, 224, 240), outline=(18, 22, 28, 255))
        nm = str(p.get("name", ""))[:14]
        if nm:
            _lbl((sx + r + 3, sy - 8), nm, fnt)

    # scale bar (bottom-left) — region tile ≈ size×0.9 km
    bx, by, bw = 22, H - 34, 150
    d.rectangle([bx, by, bx + bw, by + 6], fill=(255, 255, 255, 235), outline=(0, 0, 0, 210))
    d.rectangle([bx, by, bx + bw // 2, by + 6], fill=(20, 24, 30, 235))
    _lbl((bx, by - 17), f"~{int(cfg.size * 0.9)} km", _cfont(12))

    # north arrow (top-right)
    _lbl((W - 34, 12), "N", _cfont(16))
    d.line([(W - 28, 40), (W - 28, 16)], fill=(255, 255, 255, 235), width=2)
    d.polygon([(W - 28, 12), (W - 32, 20), (W - 24, 20)], fill=(255, 255, 255, 235))


def _terrain_enhance(E, seed, cfg):
    """Domain-warped, fBm-layered, ridge-carved, lightly thermally+hydraulically
    eroded heightfield + a normal map with micro-detail. Visual fidelity only —
    does not touch the canonical biome/data model."""
    import numpy as np
    from PIL import Image
    sea = cfg.sea_level
    Sf = E.shape[0]
    S = 512 if Sf > 512 else Sf          # work at half-res for ~4× speed, upscale after
    if S != Sf:
        E = np.asarray(Image.fromarray((np.clip(E, 0, 1) * 255).astype(np.uint8)).resize((S, S), Image.BILINEAR), dtype=np.float64) / 255.0
    # 1) domain warp → organic continents, sinuous rivers, ridgelines
    strength = 0.045
    wx = (_fbm_field(S, seed ^ 0x9E1, 4, 3.0) - 0.5) * 2 * strength * S
    wy = (_fbm_field(S, seed ^ 0x7C3, 4, 3.0) - 0.5) * 2 * strength * S
    yy, xx = np.mgrid[0:S, 0:S]
    Ew = E[np.clip((yy + wy).astype(np.int32), 0, S - 1), np.clip((xx + wx).astype(np.int32), 0, S - 1)]
    land = Ew > sea
    # 2) layered fBm detail + ridged-multifractal mountains on highlands
    detail = (_fbm_field(S, seed ^ 0x4D5, 6, 8.0) - 0.5) * 0.10
    ridge = 1.0 - np.abs(_fbm_field(S, seed ^ 0x33A, 5, 6.0) * 2.0 - 1.0)
    high = np.clip((Ew - 0.62) / 0.38, 0, 1)
    Eh = Ew + detail * land + ridge * high * 0.14 * land
    # 3) thermal erosion (talus smoothing of steep slopes)
    for _ in range(3):
        lap = np.roll(Eh, 1, 0) + np.roll(Eh, -1, 0) + np.roll(Eh, 1, 1) + np.roll(Eh, -1, 1) - 4 * Eh
        Eh = Eh + 0.12 * lap * land
    # 4) hydraulic carving — deepen concave flow lines (valleys)
    gy, gx = np.gradient(Eh)
    slope = np.sqrt(gx * gx + gy * gy)
    lap2 = np.roll(Eh, 1, 0) + np.roll(Eh, -1, 0) + np.roll(Eh, 1, 1) + np.roll(Eh, -1, 1) - 4 * Eh
    valley = np.clip(-lap2 * 40.0, 0, 1) * np.clip(slope * 6.0, 0, 1)
    Eh = np.clip(Eh - valley * 0.05 * land, 0, 1)
    # 5) normal map with micro-detail (triplanar-style surface response)
    micro = (_fbm_field(S, seed ^ 0x1B7, 4, 24.0) - 0.5) * 0.015
    En = np.clip(Eh + micro * land, 0, 1)
    gny, gnx = np.gradient(En * 7.0)
    nl = np.sqrt(gnx * gnx + gny * gny + 1.0)
    normal = np.stack([-gnx / nl, -gny / nl, np.ones_like(En) / nl], axis=-1)
    if S != Sf:
        Eh = np.asarray(Image.fromarray((np.clip(Eh, 0, 1) * 255).astype(np.uint8)).resize((Sf, Sf), Image.BILINEAR), dtype=np.float64) / 255.0
        chans = []
        for k in range(3):
            c = np.asarray(Image.fromarray(((normal[..., k] * 0.5 + 0.5) * 255).astype(np.uint8)).resize((Sf, Sf), Image.BILINEAR), dtype=np.float64) / 255.0
            chans.append(c * 2.0 - 1.0)
        normal = np.stack(chans, axis=-1)
    return Eh, normal


def _render_atlas(world: dict, cfg: WorldConfig) -> bytes:
    """Hyper-real SATELLITE relief: domain-warped + eroded heightfield, normal-map
    PBR-style lighting, slope/height materials (rock+snow), atmospheric haze,
    coastal foam + shallow-water refraction, then cartographic overlays."""
    import io
    import numpy as np
    from PIL import Image, ImageFilter
    rgb, elev, n = _grid_arrays(world)
    S = 1024
    base = np.asarray(Image.fromarray(rgb.astype(np.uint8)).resize((S, S), Image.BICUBIC), dtype=np.float64)
    E0 = np.asarray(Image.fromarray((elev * 255).astype(np.uint8)).resize((S, S), Image.BICUBIC), dtype=np.float64) / 255.0
    sea = cfg.sea_level
    Eh, normal = _terrain_enhance(E0, cfg.seed, cfg)

    sun = np.array([-0.5, -0.6, 0.62]); sun = sun / np.linalg.norm(sun)
    ndl = np.clip((normal * sun).sum(-1), 0, 1)
    shade = (0.45 + 0.85 * ndl)[..., None]
    landm = (Eh >= sea)[..., None]
    col = base * shade

    # slope/height-driven materials: rock on steep faces, snow on peaks
    gy, gx = np.gradient(Eh); slope = np.sqrt(gx * gx + gy * gy)
    rockm = (np.clip(slope * 9.0 - 0.6, 0, 1)[..., None]) * landm
    col = col * (1 - rockm * 0.5) + np.array([120., 114., 104.]) * rockm * 0.5
    snow = (np.clip((Eh - 0.84) / 0.16, 0, 1)[..., None]) * landm
    col = col * (1 - snow) + np.array([242., 246., 252.]) * snow * (0.6 + 0.4 * ndl[..., None])

    # ocean: depth gradient + specular sparkle + shallow refraction
    depth = np.clip((sea - Eh) / max(sea, 1e-3), 0, 1)[..., None]
    ocean = np.array([30., 96., 168.]) * (1 - depth * 0.6) + np.array([4., 18., 56.]) * (depth * 0.6)
    spec = (np.clip((normal * sun).sum(-1), 0, 1) ** 24)[..., None]
    ocean = ocean + spec * 120.0 * (1 - landm.astype(np.float64))
    col = np.where(landm, col, ocean)

    # coastal foam band
    lm = Image.fromarray(((Eh >= sea).astype(np.uint8)) * 255)
    edge = np.asarray(lm.filter(ImageFilter.MaxFilter(5)), dtype=np.float64) - np.asarray(lm, dtype=np.float64)
    foam = (np.asarray(Image.fromarray((edge > 40).astype(np.uint8) * 255).filter(ImageFilter.GaussianBlur(2)), dtype=np.float64) / 255.0)[..., None]
    col = col * (1 - foam * 0.8) + np.array([235., 245., 255.]) * foam * 0.8

    # atmospheric / aerial scatter haze (distance from centre) + rim vignette
    yy, xx = np.mgrid[0:S, 0:S]
    r = np.sqrt((xx - S / 2) ** 2 + (yy - S / 2) ** 2) / (S / 2)
    haze = np.clip(r * 0.45 - 0.08, 0, 0.42)[..., None]
    col = col * (1 - haze) + np.array([150., 180., 215.]) * haze
    vig = np.clip(1.10 - (r ** 2.3) * 0.55, 0.4, 1.10)[..., None]

    out = np.clip(col * vig, 0, 255).astype(np.uint8)
    img = Image.fromarray(out).filter(ImageFilter.UnsharpMask(radius=2, percent=110, threshold=2)).resize((768, 768), Image.LANCZOS)
    _atlas_overlays(img, world, cfg)
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()


def _render_blueprint(world: dict, cfg: WorldConfig) -> bytes:
    """Artsy CYAN BLUEPRINT: navy ground, glowing elevation contour lines,
    luminous coastlines, faint survey grid — a designer's schematic."""
    import io
    import numpy as np
    from PIL import Image, ImageFilter
    rgb, elev, n = _grid_arrays(world)
    S = 1024
    E = np.asarray(Image.fromarray((elev * 255).astype(np.uint8)).resize((S, S), Image.BICUBIC), dtype=np.float64) / 255.0
    sea = cfg.sea_level
    col = np.zeros((S, S, 3)) + np.array([8., 16., 38.])
    levels = np.floor(E / 0.055)
    dlx = np.abs(levels - np.roll(levels, 1, axis=1))
    dly = np.abs(levels - np.roll(levels, 1, axis=0))
    contour = (dlx + dly) > 0
    col[contour] = np.array([56., 128., 178.])
    land = (E >= sea)
    lm = Image.fromarray((land.astype(np.uint8) * 255))
    edge = np.asarray(lm.filter(ImageFilter.MaxFilter(5)), dtype=np.float64) - np.asarray(lm, dtype=np.float64)
    coast = edge > 40
    glow = np.asarray(Image.fromarray((coast.astype(np.uint8) * 255)).filter(ImageFilter.GaussianBlur(5)), dtype=np.float64) / 255.0
    col += glow[..., None] * np.array([40., 180., 235.]) * 1.7
    col[coast] = np.array([185., 240., 255.])
    grid = (np.arange(S) % 64 == 0)
    col[grid, :] += np.array([18., 46., 66.])
    col[:, grid] += np.array([18., 46., 66.])
    out = np.clip(col, 0, 255).astype(np.uint8)
    img = Image.fromarray(out).resize((768, 768), Image.LANCZOS)
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()


def _render_galaxy_nasa(world: dict, cfg: WorldConfig) -> bytes:
    """NASA-imagery-style GALAXY: logarithmic spiral arms (2-4), a blazing
    yellow bulge, blue young-star ridges, dark dust lanes, pink HII star-forming
    regions, an inclined disk, field stars + bloom — a Hubble-grade portrait."""
    import io
    import numpy as np
    from PIL import Image, ImageFilter
    S = 1024
    seed = cfg.seed & 0x7FFFFFFF
    rng = np.random.default_rng(seed)
    yy, xx = np.mgrid[0:S, 0:S].astype(np.float64)
    cx = cy = S / 2
    dx = (xx - cx) / (S / 2); dy = (yy - cy) / (S / 2)
    incl = 0.55 + (seed % 30) / 100.0          # disk inclination → 3D feel
    dyi = dy / incl
    r = np.sqrt(dx * dx + dyi * dyi)
    theta = np.arctan2(dyi, dx)
    arms = 2 + (seed % 3)                        # 2..4 spiral arms
    twist = 4.5 + (seed % 60) / 12.0
    logr = np.log(r + 0.06)
    spiral = np.cos(arms * (theta - twist * logr))
    arm = np.clip((spiral - 0.15) / 0.85, 0, 1) ** 1.7
    disk = np.exp(-r * 2.0)
    density = arm * disk
    bulge = np.exp(-(r * 4.2) ** 2)
    col = np.zeros((S, S, 3))
    col += density[..., None] * np.array([140., 175., 255.]) * 1.8       # arm blue
    col += (density ** 2.5)[..., None] * np.array([205., 218., 255.]) * 1.2  # bright ridges
    col += bulge[..., None] * np.array([255., 220., 140.]) * 2.7         # golden core
    dust = np.clip(np.cos(arms * (theta - twist * logr) + 0.7), 0, 1) * np.exp(-r * 2.6)
    col *= (1 - dust[..., None] * 0.55)                                  # dust lanes
    # HII pink star-forming regions along the arms
    K = 260
    ang = rng.uniform(-math.pi, math.pi, K)
    rr = rng.uniform(0.12, 0.93, K)
    px = (cx + np.cos(ang) * rr * (S / 2)).astype(int)
    py = (cy + np.sin(ang) * rr * incl * (S / 2)).astype(int)
    for i in range(K):
        x_, y_ = px[i], py[i]
        if 0 <= x_ < S and 0 <= y_ < S and density[y_, x_] > 0.16:
            c = np.array([255., 120., 170.]) if rng.random() < 0.55 else np.array([150., 200., 255.])
            col[max(0, y_ - 1):y_ + 2, max(0, x_ - 1):x_ + 2] += c * 1.3
    col += _starfield(S, seed ^ 0xA11, density=0.0016, bright=1.1)
    bright = np.where(col.mean(-1)[..., None] > 70, col, 0).astype(np.uint8)
    bloom = np.asarray(Image.fromarray(bright).filter(ImageFilter.GaussianBlur(9)), dtype=np.float64) * 1.3
    col = col + bloom
    rv = np.sqrt(dx * dx + dy * dy)
    vig = np.clip(1.0 - (rv ** 2.4) * 0.55, 0.15, 1.0)[..., None]
    out = np.clip(col * vig, 0, 255).astype(np.uint8)
    img = Image.fromarray(out).resize((768, 768), Image.LANCZOS)
    buf = io.BytesIO(); img.save(buf, format="PNG"); return buf.getvalue()


def _render_globe_gif(cfg: WorldConfig, frames: int = 18, size: int = 320) -> bytes:
    """A seamlessly-looping animated GIF of the planet slowly rotating."""
    import io
    from PIL import Image
    cfg.size = max(cfg.size, 64); cfg.octaves = max(cfg.octaves, 5)
    world = build_world(cfg)
    imgs = []
    for i in range(frames):
        png = _render_globe(world, cfg, lon_offset=i / frames, out_size=size)
        imgs.append(Image.open(io.BytesIO(png)).convert("RGB").convert("P", palette=Image.ADAPTIVE, colors=96))
    buf = io.BytesIO()
    imgs[0].save(buf, format="GIF", save_all=True, append_images=imgs[1:],
                 duration=90, loop=0, optimize=True, disposal=2)
    return buf.getvalue()


def _render_export(cfg: WorldConfig, mode: str, caption: str) -> bytes:
    import io
    from PIL import Image, ImageDraw
    png = _render_world_hi(cfg, mode)
    base = Image.open(io.BytesIO(png)).convert("RGB")
    W = base.width
    foot = 92
    canvas = Image.new("RGB", (W, base.height + foot), (8, 9, 18))
    canvas.paste(base, (0, 0))
    d = ImageDraw.Draw(canvas)
    d.line([(0, base.height), (W, base.height)], fill=(40, 52, 78), width=2)
    d.text((24, base.height + 16), (caption or cfg.scale.title())[:42], fill=(226, 232, 240), font=_cfont(32))
    sub = f"Forged in Worldforge · {cfg.scale} · {cfg.palette}/{cfg.climate} · seed {cfg.seed} · {mode}"
    d.text((24, base.height + 56), sub, fill=(120, 142, 172), font=_cfont(18))
    from core.render_quality import EXTREME_PX
    scale = EXTREME_PX / W
    canvas = canvas.resize((EXTREME_PX, int(canvas.height * scale)), Image.LANCZOS)
    buf = io.BytesIO(); canvas.save(buf, format="PNG"); return buf.getvalue()


