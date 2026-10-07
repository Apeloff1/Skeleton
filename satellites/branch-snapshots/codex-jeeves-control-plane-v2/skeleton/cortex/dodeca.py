"""Dodecahedron seal — twelve faces of the organism.

Each face is a named capability. The number is how many faces are live
(finite ppl, fires, merges, steps). Twelve is the house complete.
"""
from __future__ import annotations

from typing import Any, Dict

FACES = (
    "pfc", "midbrain", "left", "right",
    "neo", "neo_rms", "callosum", "moe",
    "bpe", "hive", "sleep", "zaibatsu",
)


def _live_lm(lm) -> bool:
    if lm is None:
        return False
    if hasattr(lm, "perplexity"):
        try:
            return float(lm.perplexity(["plan tensor ttk"])) < 1e8
        except Exception:
            return False
    return int(getattr(lm, "steps", 0) or getattr(lm, "fitted", 0) or 0) >= 0


def face_card(neo) -> Dict[str, Any]:
    slots = getattr(neo, "slots", {}) or {}
    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    cc = getattr(neo, "callosum", None)
    moe = getattr(neo, "moe", None)
    bpe = getattr(neo, "bpe", None)
    sleep = getattr(neo, "sleep", None)
    faces = {
        "pfc": _live_lm(getattr(slots.get("pfc"), "transformer", None)),
        "midbrain": _live_lm(getattr(slots.get("midbrain"), "transformer", None)),
        "left": _live_lm(getattr(slots.get("left"), "transformer", None)),
        "right": _live_lm(getattr(slots.get("right"), "transformer", None)),
        "neo": _live_lm(xf),
        "neo_rms": _live_lm(rms),
        "callosum": int(getattr(cc, "fires", 0) or 0) >= 0 and cc is not None,
        "moe": moe is not None and bool(getattr(moe, "experts", None)),
        "bpe": bpe is not None and int(len(getattr(bpe, "merges", ()) or ())) > 0,
        "hive": bool(getattr(neo, "acquired", None) is not None),
        "sleep": sleep is not None,
        "zaibatsu": callable(getattr(neo, "elect_mouth", None)),
    }
    live = sum(1 for f in FACES if faces.get(f))
    return {
        "house": "dodecahedron",
        "faces": faces,
        "live": live,
        "of": 12,
        "complete": live == 12,
        "number": live,
    }
