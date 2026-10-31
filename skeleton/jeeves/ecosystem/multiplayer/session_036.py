"""Multiplayer session template 036.
"""
from __future__ import annotations

SESSION = "session_036"
MAX_PEERS = 4 + (36 % 5)

def open_session(host: str) -> dict:
    if not host:
        return {"ok": False, "reason": "no_host"}
    return {"ok": True, "session": SESSION, "host": host, "max_peers": MAX_PEERS, "tick_rate": 20}

def pack_delta(state: dict, peers: list[str]) -> dict:
    if not isinstance(state, dict):
        return {"ok": False, "reason": "bad_state"}
    priority = sorted(state.keys())[:8]
    return {"ok": True, "session": SESSION, "priority": priority, "peers": peers[:MAX_PEERS]}
