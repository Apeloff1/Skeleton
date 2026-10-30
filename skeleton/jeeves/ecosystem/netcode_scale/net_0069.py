"""Netcode scale 0069.
"""
from __future__ import annotations

NET = "net_scale_0069"

def tick(state: dict, peers: list[str]) -> dict:
    if not isinstance(state, dict):
        return {"ok": False, "reason": "bad_state"}
    return {"ok": True, "net": NET, "peers": peers[:8], "delta": sorted(state.keys())[:6]}
