"""Kernel router — which stages fire on this box, this pulse.

Rules, not essays:
  tight   → skip gpu, speculate, radix, fuse, gossip
  mobile  → skip speculate, radix, election
  pressure ≥ 0.82 → skip gpu, block uses fused only, reclaim on
  throttle deny   → stop after admit
"""
from __future__ import annotations

from typing import Any, Dict, List, Set

SKIP = {
    "tight": frozenset({"gpu", "speculate", "radix", "fuse", "gossip", "saga", "election"}),
    "mobile": frozenset({"speculate", "radix", "election", "saga"}),
    "desktop": frozenset(),
    "max": frozenset(),
}


EDGES = {
    "admit": ("quota",),
    "quota": ("place",),
    "place": ("prefill",),
    "prefill": ("decode",),
    "decode": ("check",),
    "check": ("stock",),
    "stock": ("reclaim",),
    "reclaim": (),
}


def plan(profile: str, *, pressure: float = 0.0, blocked: bool = False,
         slo_trip: bool = False) -> Dict[str, Any]:
    skip: Set[str] = set(SKIP.get(str(profile), ()))
    if pressure >= 0.82 or slo_trip:
        skip.update({"gpu", "speculate", "prefetch"})
    stages = ["admit", "quota", "place", "prefill", "decode", "check", "stock", "reclaim"]
    if blocked:
        stages = ["admit"]
        skip.update({"prefill", "decode", "place"})
    run = [s for s in stages if s not in skip]
    decode_n = 1 if profile in {"tight", "mobile"} or pressure >= 0.62 else 3
    if slo_trip:
        decode_n = 1
    return {
        "kind": "krouter",
        "profile": profile,
        "pressure": round(float(pressure), 4),
        "run": run,
        "skip": sorted(skip),
        "blocked": int(blocked),
        "slo_trip": int(slo_trip),
        "decode_n": decode_n,
        "edges": {k: list(v) for k, v in EDGES.items() if k in run},
        "stored_prose": 0,
    }
