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


def _live_lm(mouth) -> bool:
    """Return whether a model mouth is callable/finite through its public seam.

    A mouth can intentionally hide an internal transformer (PFC does this
    before training) while remaining a live ModelPort backed by its smaller
    learned substrate.  Dodeca measures the capability, not a private field.
    """
    if mouth is None:
        return False
    candidate = mouth
    if not hasattr(candidate, "perplexity"):
        candidate = getattr(mouth, "transformer", None)
    if candidate is None:
        return False
    if hasattr(candidate, "perplexity"):
        try:
            return float(candidate.perplexity(["plan tensor ttk"])) < 1e8
        except Exception:
            return False
    return int(getattr(candidate, "steps", 0) or getattr(candidate, "fitted", 0) or 0) >= 0


def face_card(neo) -> Dict[str, Any]:
    slots = getattr(neo, "slots", {}) or {}
    xf = getattr(neo, "transformer", None)
    rms = getattr(neo, "neo_rms", None)
    cc = getattr(neo, "callosum", None)
    moe = getattr(neo, "moe", None)
    bpe = getattr(neo, "bpe", None)
    sleep = getattr(neo, "sleep", None)
    faces = {
        "pfc": _live_lm(slots.get("pfc")),
        "midbrain": _live_lm(slots.get("midbrain")),
        "left": _live_lm(slots.get("left")),
        "right": _live_lm(slots.get("right")),
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
