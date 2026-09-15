"""
gameforge.media.cinematic — top-end studio post-processing.

Turns a flat game render into a cinematic frame: filmic color-grade, bloom on
highlights, atmospheric haze, radial vignette, subtle film grain and a 2.39:1
letterbox. Masks are cached per (W,H) so it stays fast enough for video.
"""
from __future__ import annotations

from typing import Dict, Tuple

import numpy as np
from PIL import Image, ImageFilter

# per-mood filmic grade (channel gain, lift) — warm ember, cool night, etc.
_GRADES = {
    "ember":  (np.array([1.14, 1.02, 0.86]), np.array([10, 4, -6])),
    "night":  (np.array([0.92, 0.98, 1.12]), np.array([-4, 0, 10])),
    "forest": (np.array([0.95, 1.10, 0.95]), np.array([-2, 8, -2])),
    "dusk":   (np.array([1.12, 0.98, 1.05]), np.array([8, 0, 6])),
}
_VIGNETTE: Dict[Tuple[int, int], np.ndarray] = {}


def _vignette_mask(W: int, H: int) -> np.ndarray:
    key = (W, H)
    if key in _VIGNETTE:
        return _VIGNETTE[key]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    cx, cy = W / 2.0, H / 2.0
    d = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    mask = np.clip(1.0 - (d ** 2.2) * 0.55, 0.35, 1.0).astype(np.float32)
    m = mask[:, :, None]
    _VIGNETTE[key] = m
    return m


def grade(img: Image.Image, mood: str = "ember", bloom: bool = True,
          grain: float = 0.04, letterbox: bool = True) -> Image.Image:
    W, H = img.size
    arr = np.asarray(img.convert("RGB")).astype(np.float32)

    # 1) bloom — blur bright regions, screen-blend back
    if bloom:
        lum = arr.mean(axis=2)
        bright = np.clip((lum - 165) / 90.0, 0, 1)[:, :, None] * arr
        bimg = Image.fromarray(bright.astype(np.uint8)).filter(ImageFilter.GaussianBlur(7))
        b = np.asarray(bimg).astype(np.float32)
        arr = 255.0 - (255.0 - arr) * (255.0 - b * 0.85) / 255.0

    # 2) filmic color grade
    gain, lift = _GRADES.get(mood, _GRADES["ember"])
    arr = arr * gain[None, None, :] + lift[None, None, :]

    # 3) atmospheric haze near the horizon (lower third lifted, desaturated)
    haze = np.linspace(0, 1, H)[:, None, None] ** 3
    haze_col = np.array([70, 60, 95], dtype=np.float32)
    arr = arr * (1 - 0.18 * haze) + haze_col[None, None, :] * (0.18 * haze)

    # 4) vignette
    arr = arr * _vignette_mask(W, H)

    # 5) contrast S-curve
    arr = 255.0 * np.clip((arr / 255.0 - 0.5) * 1.12 + 0.5, 0, 1)

    # 6) film grain
    if grain > 0:
        noise = (np.random.rand(H, W, 1).astype(np.float32) - 0.5) * (grain * 255.0)
        arr = arr + noise

    arr = np.clip(arr, 0, 255).astype(np.uint8)
    out = Image.fromarray(arr)

    # 7) 2.39:1 letterbox bars
    if letterbox:
        bar = int(H * 0.055)
        d = np.asarray(out).copy()
        d[:bar, :, :] = 0
        d[H - bar:, :, :] = 0
        out = Image.fromarray(d)
    return out


__all__ = ["grade"]
