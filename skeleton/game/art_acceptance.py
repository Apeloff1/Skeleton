"""GF-I art-direction visual acceptance checks for renderer screenshot-reference tests.

Pure, deterministic, stdlib-only. Frames are row-major lists of rows of
(r, g, b) int tuples (0-255); masks are lists of rows of bools (True = subject).
No GPU, no image decoding: renderer lanes (GF-I code owners) supply pixels.

Contract: docs/plan/GAME_FRONTIER_ART_DIRECTION_GF_I_2026_10_24.md
Supports TODO items GF-P0-13, GF-P0-35, GF-P0-57 (screenshot-reference
acceptance only). Does NOT close GF-P0-60, GF-P0-61 or GF-P0-165.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

RGB = Tuple[int, int, int]
Frame = Sequence[Sequence[RGB]]
Mask = Sequence[Sequence[bool]]

TOKENS_PATH = Path(__file__).resolve().parents[2] / "design" / "art" / "visual_identity_tokens.json"

# Fallback mirrors design/art/visual_identity_tokens.json (source: design_guidelines.json).
_FALLBACK_PALETTE = {
    "surface": "#0A0A0A", "onSurface": "#E5E5E5", "surfaceSecondary": "#141414",
    "surfaceTertiary": "#1F1F1F", "brand": "#8B5CF6", "brandSecondary": "#A78BFA",
    "brandTertiary": "#2E1B5B", "success": "#10B981", "warning": "#F59E0B",
    "error": "#EF4444", "info": "#3B82F6", "border": "#262626", "borderStrong": "#404040",
}

# Thresholds (art-direction bar). Changing these is an Art Director decision.
MIN_CONTRAST_RATIO = 3.0          # subject vs background, WCAG-style relative luminance
MIN_SILHOUETTE_FILL = 0.02        # subject must occupy >= 2% of frame (thumbnail read)
MAX_SILHOUETTE_FILL = 0.85        # and not swallow the frame
MIN_PALETTE_CONFORMANCE = 0.90    # share of pixels within tolerance of a token colour
PALETTE_TOLERANCE = 48.0          # Euclidean RGB distance
VALUE_BANDS = (("shadow", 0.0, 0.25), ("mid", 0.25, 0.70), ("highlight", 0.70, 1.0001))
MIN_BANDS_PRESENT = 2             # flat frames (one band) fail
MIN_BAND_SHARE = 0.01


def hex_to_rgb(value: str) -> RGB:
    v = value.lstrip("#")
    if len(v) != 6:
        raise ValueError(f"bad hex colour: {value!r}")
    return (int(v[0:2], 16), int(v[2:4], 16), int(v[4:6], 16))


def load_palette(path: Optional[Path] = None) -> Dict[str, RGB]:
    p = Path(path) if path else TOKENS_PATH
    try:
        colors = json.loads(p.read_text(encoding="utf-8"))["colors"]
    except (OSError, KeyError, ValueError):
        colors = _FALLBACK_PALETTE
    return {k: hex_to_rgb(v) for k, v in sorted(colors.items())}


def _lin(c: int) -> float:
    s = c / 255.0
    return s / 12.92 if s <= 0.04045 else ((s + 0.055) / 1.055) ** 2.4


def relative_luminance(px: RGB) -> float:
    r, g, b = px
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def _pixels(frame: Frame) -> Iterable[RGB]:
    for row in frame:
        for px in row:
            yield px


def _check_shape(frame: Frame, mask: Optional[Mask] = None) -> Tuple[int, int]:
    h = len(frame)
    if h == 0 or len(frame[0]) == 0:
        raise ValueError("empty frame")
    w = len(frame[0])
    if any(len(r) != w for r in frame):
        raise ValueError("ragged frame")
    if mask is not None and (len(mask) != h or any(len(r) != w for r in mask)):
        raise ValueError("mask shape does not match frame")
    return h, w


def value_band_histogram(frame: Frame) -> Dict[str, float]:
    h, w = _check_shape(frame)
    counts = {name: 0 for name, _, _ in VALUE_BANDS}
    for px in _pixels(frame):
        y = relative_luminance(px) ** (1 / 2.2)  # perceptual-ish value
        for name, lo, hi in VALUE_BANDS:
            if lo <= y < hi:
                counts[name] += 1
                break
    n = float(h * w)
    return {k: counts[k] / n for k in counts}


def _mean_luminance(frame: Frame, mask: Mask, want: bool) -> Optional[float]:
    total, n = 0.0, 0
    for row, mrow in zip(frame, mask):
        for px, m in zip(row, mrow):
            if bool(m) == want:
                total += relative_luminance(px)
                n += 1
    return total / n if n else None


def contrast_ratio(frame: Frame, mask: Mask) -> float:
    _check_shape(frame, mask)
    a = _mean_luminance(frame, mask, True)
    b = _mean_luminance(frame, mask, False)
    if a is None or b is None:
        return 1.0
    hi, lo = max(a, b), min(a, b)
    return (hi + 0.05) / (lo + 0.05)


def silhouette_fill_ratio(mask: Mask) -> float:
    h = len(mask)
    if h == 0 or len(mask[0]) == 0:
        raise ValueError("empty mask")
    on = sum(1 for row in mask for m in row if m)
    return on / float(h * len(mask[0]))


def palette_conformance(frame: Frame, palette: Optional[Dict[str, RGB]] = None,
                        tolerance: float = PALETTE_TOLERANCE) -> float:
    _check_shape(frame)
    pal = list((palette or load_palette()).values())
    tol2 = tolerance * tolerance
    ok = n = 0
    for px in _pixels(frame):
        n += 1
        if any((px[0]-c[0])**2 + (px[1]-c[1])**2 + (px[2]-c[2])**2 <= tol2 for c in pal):
            ok += 1
    return ok / float(n)


@dataclass
class AcceptanceReport:
    passed: bool
    metrics: Dict[str, float]
    failures: List[str] = field(default_factory=list)
    supports: Tuple[str, ...] = ("GF-P0-13", "GF-P0-35", "GF-P0-57")
    not_claimed: Tuple[str, ...] = ("GF-P0-60", "GF-P0-61", "GF-P0-165")


def evaluate_frame(frame: Frame, mask: Mask,
                   palette: Optional[Dict[str, RGB]] = None) -> AcceptanceReport:
    """Run the full art-direction acceptance contract on one reference frame."""
    _check_shape(frame, mask)
    bands = value_band_histogram(frame)
    cr = contrast_ratio(frame, mask)
    fill = silhouette_fill_ratio(mask)
    conf = palette_conformance(frame, palette)
    present = sum(1 for v in bands.values() if v >= MIN_BAND_SHARE)
    failures: List[str] = []
    if present < MIN_BANDS_PRESENT:
        failures.append(f"value_bands: {present} band(s) present < {MIN_BANDS_PRESENT} (flat frame)")
    if cr < MIN_CONTRAST_RATIO:
        failures.append(f"contrast: {cr:.2f} < {MIN_CONTRAST_RATIO}")
    if not (MIN_SILHOUETTE_FILL <= fill <= MAX_SILHOUETTE_FILL):
        failures.append(f"silhouette_fill: {fill:.3f} outside [{MIN_SILHOUETTE_FILL}, {MAX_SILHOUETTE_FILL}]")
    if conf < MIN_PALETTE_CONFORMANCE:
        failures.append(f"palette_conformance: {conf:.3f} < {MIN_PALETTE_CONFORMANCE}")
    metrics = {"contrast_ratio": round(cr, 4), "silhouette_fill": round(fill, 4),
               "palette_conformance": round(conf, 4), "bands_present": float(present)}
    metrics.update({f"band_{k}": round(v, 4) for k, v in bands.items()})
    return AcceptanceReport(passed=not failures, metrics=metrics, failures=failures)
