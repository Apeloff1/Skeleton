"""Multiplayer session.
Host/client roles, tick sync, and optical-weighted state replication.
"""
from typing import Any, Dict, List

class MultiplayerSession:
    def __init__(self):
        self.peers: Dict[str, Dict[str, Any]] = {}
        self.tick = 0

    def join(self, peer_id: str, role: str = "client") -> Dict[str, Any]:
        self.peers[peer_id] = {"role": role, "optical": 0.93, "state": {}}
        return {"ok": True, "peer": peer_id, "role": role}

    def sync(self, peer_id: str, state: Dict[str, Any], optical: float) -> Dict[str, Any]:
        if peer_id not in self.peers:
            return {"ok": False}
        self.tick += 1
        self.peers[peer_id]["state"] = state
        self.peers[peer_id]["optical"] = optical
        return {"ok": True, "tick": self.tick, "peers": len(self.peers)}

    def status(self) -> Dict[str, Any]:
        return {"peers": len(self.peers), "tick": self.tick, "schema": "skeleton.multiplayer.v1"}
