"""Worldforge noise primitives — deterministic value-noise / fBm / ridged-noise.

Extracted from worldforge.py (Session 13c refactor). Pure, dependency-free leaf
utilities: a hash-based PRNG plus smooth value noise and its fractal variants.
Determinism here is load-bearing — the same (x, y, seed) MUST always return the
same float, or generated worlds stop being reproducible.
"""
from __future__ import annotations

import math


def _h01(ix, iy, seed):
    h = (ix * 374761393 + iy * 668265263 + seed * 2246822519) & 0xFFFFFFFF
    h = (h ^ (h >> 13)) * 1274126177 & 0xFFFFFFFF
    h = h ^ (h >> 16)
    return (h & 0xFFFFFFFF) / 0xFFFFFFFF


def _smooth(t):
    return t * t * (3 - 2 * t)


def _vnoise(x, y, seed):
    x0, y0 = math.floor(x), math.floor(y)
    fx, fy = _smooth(x - x0), _smooth(y - y0)
    v00 = _h01(x0, y0, seed); v10 = _h01(x0 + 1, y0, seed)
    v01 = _h01(x0, y0 + 1, seed); v11 = _h01(x0 + 1, y0 + 1, seed)
    return (v00 * (1 - fx) + v10 * fx) * (1 - fy) + (v01 * (1 - fx) + v11 * fx) * fy


def _fbm(x, y, seed, octaves=5):
    total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
    for o in range(octaves):
        total += amp * _vnoise(x * freq, y * freq, seed + o * 1013)
        norm += amp; amp *= 0.5; freq *= 2.0
    return total / norm


def _ridged(x, y, seed, octaves=4):
    total, amp, freq, norm = 0.0, 1.0, 1.0, 0.0
    for o in range(octaves):
        n = 1.0 - abs(2.0 * _vnoise(x * freq, y * freq, seed + o * 2027) - 1.0)
        total += amp * (n * n)
        norm += amp; amp *= 0.5; freq *= 2.0
    return total / norm
