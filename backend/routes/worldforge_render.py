"""Worldforge render primitives — pure, self-contained drawing/array helpers
(stdlib + numpy + PIL only). Extracted from worldforge.py; imported one-way
by routes.worldforge. No worldforge constants, no DB, no LLM, no router."""
from __future__ import annotations

import os
import math
import random

import numpy as np
from PIL import Image, ImageDraw, ImageFont


def _shade_hex(hex_color, mult):
    r = max(0, min(255, int(int(hex_color[1:3], 16) * mult)))
    g = max(0, min(255, int(int(hex_color[3:5], 16) * mult)))
    b = max(0, min(255, int(int(hex_color[5:7], 16) * mult)))
    return f"#{r:02x}{g:02x}{b:02x}"


def _hue_of(hexstr: str) -> float:
    r, g, b = (int(hexstr[i:i + 2], 16) / 255 for i in (0, 2, 4))
    mx, mn = max(r, g, b), min(r, g, b)
    if mx == mn:
        return -1.0
    d = mx - mn
    if mx == r:
        h = ((g - b) / d) % 6
    elif mx == g:
        h = (b - r) / d + 2
    else:
        h = (r - g) / d + 4
    return h * 60


def _grid_arrays(world: dict):
    """Convert a built world's tile grid → numpy RGB (H,W,3 float) + elevation (H,W)."""
    import numpy as np
    g = world["grid"]
    n = world["size"]
    rgb = np.empty((n, n, 3), dtype=np.float64)
    elev = np.empty((n, n), dtype=np.float64)
    for y in range(n):
        row = g[y]
        for x in range(n):
            c = row[x]["c"]
            rgb[y, x, 0] = int(c[1:3], 16)
            rgb[y, x, 1] = int(c[3:5], 16)
            rgb[y, x, 2] = int(c[5:7], 16)
            elev[y, x] = row[x].get("e", 0.5)
    return rgb, elev, n


def _bilinear(arr, gx, gy, n):
    """Vectorised bilinear sample of arr[H,W,(C)] at float coords gx,gy (clamped)."""
    import numpy as np
    gx = np.clip(gx, 0, n - 1.001); gy = np.clip(gy, 0, n - 1.001)
    x0 = np.floor(gx).astype(int); y0 = np.floor(gy).astype(int)
    x1 = x0 + 1; y1 = y0 + 1
    fx = (gx - x0)[..., None] if arr.ndim == 3 else (gx - x0)
    fy = (gy - y0)[..., None] if arr.ndim == 3 else (gy - y0)
    a = arr[y0, x0]; b = arr[y0, x1]; c = arr[y1, x0]; d = arr[y1, x1]
    return (a * (1 - fx) + b * fx) * (1 - fy) + (c * (1 - fx) + d * fx) * fy


def _starfield(S, seed, density=0.0016, bright=1.0):
    import numpy as np
    rng = np.random.default_rng(seed & 0x7FFFFFFF)
    bg = np.zeros((S, S, 3))
    nstars = int(S * S * density)
    sx = rng.integers(0, S, nstars); sy = rng.integers(0, S, nstars)
    mag = (rng.random(nstars) ** 3 * 255 * bright)
    tint = rng.random((nstars, 3)) * 0.4 + 0.6
    for i in range(nstars):
        bg[sy[i], sx[i]] = mag[i] * tint[i]
    return bg


def _cfont(sz):
    from PIL import ImageFont
    base = os.path.join(os.path.dirname(os.path.dirname(__file__)), "assets", "fonts")
    for name in ("VeraSe.ttf", "Vera.ttf", "VeraBd.ttf"):
        try:
            return ImageFont.truetype(os.path.join(base, name), sz)
        except Exception:
            continue
    return ImageFont.load_default()


def _lerp_cmap(v, stops):
    v = max(0.0, min(1.0, v))
    for i in range(len(stops) - 1):
        a, ca = stops[i]; b, cb = stops[i + 1]
        if v <= b:
            t = (v - a) / max(1e-6, (b - a))
            return tuple(int(ca[k] + (cb[k] - ca[k]) * t) for k in range(3))
    return stops[-1][1]


def _fbm_field(S, seed, octaves=5, freq=4.0):
    """Layered fractal value noise (fBm) field in [0,1] — deterministic per seed."""
    import numpy as np
    from PIL import Image
    rng = np.random.default_rng(seed & 0x7FFFFFFF)
    acc = np.zeros((S, S)); amp = 0.5; tot = 0.0; f = freq
    for _ in range(octaves):
        g = int(max(2, round(f)))
        nz = rng.random((g, g))
        layer = np.asarray(Image.fromarray((nz * 255).astype(np.uint8)).resize((S, S), Image.BICUBIC), dtype=np.float64) / 255.0
        acc += layer * amp; tot += amp; amp *= 0.5; f *= 2.0
    return acc / max(tot, 1e-6)
