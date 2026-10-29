"""Multiplayer tick.
Host/client tick with optical priority.
"""
from typing import Any, Dict

class MultiplayerTick:
    def sync(self, peers: int, tick: int, optical: float) -> Dict[str, Any]:
        if not isinstance(peers, int) or peers < 1 or not isinstance(tick, int):
            return {"ok": False, "reason": "bad_types", "schema": "skeleton.multi.tick.v1"}
        return {"ok": True, "peers": peers, "tick": tick, "optical": optical, "priority": round(optical, 2), "reason": "ok", "schema": "skeleton.multi.tick.v1"}
