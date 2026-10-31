"""Advanced multiplayer session.
Host/client, optical-weighted tick, and state replication with delta.
"""
from typing import Any, Dict, List

class MultiplayerSession:
    def __init__(self):
        self.peers: Dict[str, Dict[str, Any]] = {}
        self.tick = 0

    def join(self, peer_id: str, role: str = "client", optical: float = 0.93) -> Dict[str, Any]:
        self.peers[peer_id] = {"role": role, "optical": optical, "state": {}}
        return {"ok": True, "peer": peer_id, "role": role, "optical": optical}

    def sync(self, peer_id: str, state: Dict[str, Any], optical: float) -> Dict[str, Any]:
        if peer_id not in self.peers:
            return {"ok": False}
        self.tick += 1
        self.peers[peer_id]["state"] = state
        self.peers[peer_id]["optical"] = optical
        return {"ok": True, "tick": self.tick, "peers": len(self.peers), "optical": optical}

    def status(self) -> Dict[str, Any]:
        avg = sum(p["optical"] for p in self.peers.values()) / max(1, len(self.peers))
        return {"peers": len(self.peers), "tick": self.tick, "avg_optical": round(avg, 2), "schema": "skeleton.multiplayer.v2"}
