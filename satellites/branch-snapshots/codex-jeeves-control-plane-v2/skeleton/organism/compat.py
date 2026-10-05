"""Compatibility matrix — style × mechanic × tone. 1 = coherent, 0 = clash."""
from __future__ import annotations

from typing import Any, Dict, Tuple

STYLES = ("sci-fi", "fantasy", "cyberpunk", "wasteland")
MECHS = ("tactical", "real-time", "turn-based", "puzzle-based")
TONES = ("grim", "playful", "mythic", "clinical")

# default 1; known clashes 0
CLASH: Tuple[Tuple[str, str, str], ...] = (
    ("fantasy", "real-time", "clinical"),
    ("wasteland", "puzzle-based", "playful"),
)


def score(style: str, mech: str, tone: str) -> int:
    trip = (str(style), str(mech), str(tone))
    return 0 if trip in CLASH else 1


def card(spec: Dict[str, Any] | None = None) -> Dict[str, Any]:
    spec = spec or {}
    style = str((spec.get("era") or "sci-fi")).split("_")[0]
    if style == "extraction":
        style = "sci-fi"
    if style == "medieval":
        style = "fantasy"
    if style == "neon":
        style = "cyberpunk"
    mech = str((spec.get("pillars") or ["tactical"])[0])
    tone = "grim" if style in {"wasteland", "cyberpunk"} else "mythic" if style == "fantasy" else "clinical"
    ok = score(style, mech, tone)
    return {
        "kind": "compat",
        "style": style,
        "mech": mech,
        "tone": tone,
        "ok": ok,
        "stored_prose": 0,
    }
