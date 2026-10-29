"""Netcode 0080.
"""
from __future__ import annotations

NET = "net_0080"

def tick(state: dict, peers: list[str]) -> dict:
    if not isinstance(state, dict):
        return {"ok": False, "reason": "bad_state"}
    return {"ok": True, "net": NET, "peers": peers[:8], "delta": sorted(state.keys())[:6]}
