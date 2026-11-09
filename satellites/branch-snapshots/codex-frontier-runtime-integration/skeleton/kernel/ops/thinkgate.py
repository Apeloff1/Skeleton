"""Think-gate — decide whether this stimulus earns a loop.

Reasoning tokens open the gate. Greetings do not.
"""
from __future__ import annotations

from typing import Any, Dict

from skeleton.kernel.ops._stat import bump

NEEDLES = (
    "why", "how", "reason", "proof", "loop", "think", "plan",
    "derive", "solve", "depth", "recur", "latent",
    "smelt", "huginn", "ouro", "nanbeige", "recurrent",
)


def gated(text: str = "") -> Dict[str, Any]:
    t = str(text or "").lower()
    hits = [n for n in NEEDLES if n in t]
    bump(1)
    return {
        "kind": "think-gate",
        "open": int(bool(hits)),
        "hits": hits,
        "stored_prose": 0,
    }
