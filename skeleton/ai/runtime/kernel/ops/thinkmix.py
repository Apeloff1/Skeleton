"""Think-mix — gate + select + run one looped family on a seed row."""
from __future__ import annotations

from typing import Any, Dict, List

from skeleton.kernel.ops.budgetr import budget
from skeleton.kernel.ops.kselect import pick
from skeleton.kernel.ops.loop import unroll
from skeleton.kernel.ops.loopfuse import loopfuse
from skeleton.kernel.ops.smelt import smelt
from skeleton.kernel.ops.thinkgate import gated

Row = List[float]


def thinkmix(text: str = "", x: Row | None = None, *, profile: str = "mobile") -> Dict[str, Any]:
    g = gated(text)
    seed = list(x or [0.2, -0.1, 0.4, 0.05])
    if not g.get("open"):
        return {"kind": "think-mix", "open": 0, "family": "", "stored_prose": 0}
    fam = str(pick(profile=profile, loop=True, kv=16 if "proof" in text.lower() else 4).get("family") or "loop")
    r = int(budget(profile=profile, want=2, halt=True).get("r") or 2)
    if fam == "smelt":
        out = smelt(seed, layers=8)
    elif fam == "loop":
        out = loopfuse(seed, r=r)
    else:
        out = unroll(seed, r=r)
    return {
        "kind": "think-mix",
        "open": 1,
        "family": fam,
        "r": r,
        "run": out.get("kind"),
        "h": out.get("h"),
        "stored_prose": 0,
    }
