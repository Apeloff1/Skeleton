"""Multiplayer advanced 0145.
"""
from __future__ import annotations

MP = "mp_adv_0145"

def open_session(host: str, max_peers: int = 4) -> dict:
    if not host:
        return {"ok": False, "reason": "no_host"}
    return {"ok": True, "mp": MP, "host": host, "max_peers": max(2, min(16, max_peers)), "tick": 20}

def pack_delta(state: dict) -> dict:
    if not isinstance(state, dict):
        return {"ok": False, "reason": "bad_state"}
    return {"ok": True, "mp": MP, "priority": sorted(state.keys())[:8]}
