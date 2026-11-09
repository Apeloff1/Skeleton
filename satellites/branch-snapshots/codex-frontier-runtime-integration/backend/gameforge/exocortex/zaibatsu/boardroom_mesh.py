from __future__ import annotations
"""
Boardroom mesh — every room is interconnected to the boardroom.
Uplink / downlink / lateral edges for VOX-style routing and DNA progress.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set


def _ts() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class MeshEdge:
    from_id: str
    to_id: str
    kind: str  # uplink | downlink | lateral | audit
    weight: float = 1.0

    def to_dict(self) -> dict:
        return asdict(self)


class BoardroomMesh:
    """
    Star + ring: all rooms uplink to boardroom; boardroom downlinks to all;
    lateral edges within same division for sandbox meld.
    """

    BOARDROOM = "boardroom"

    def __init__(self):
        self.nodes: Set[str] = {self.BOARDROOM}
        self.edges: List[MeshEdge] = []
        self._edge_set: Set[tuple] = set()
        self.traffic: List[dict] = []

    def _add_edge(self, a: str, b: str, kind: str, weight: float = 1.0):
        key = (a, b, kind)
        if key in self._edge_set:
            return
        self._edge_set.add(key)
        self.edges.append(MeshEdge(from_id=a, to_id=b, kind=kind, weight=weight))

    def register_room(self, room_id: str, division: str = "Other"):
        if room_id == self.BOARDROOM:
            self.nodes.add(room_id)
            return
        self.nodes.add(room_id)
        # mandatory interconnect to boardroom
        self._add_edge(room_id, self.BOARDROOM, "uplink", 1.0)
        self._add_edge(self.BOARDROOM, room_id, "downlink", 1.0)
        self._add_edge(room_id, self.BOARDROOM, "audit", 0.5)

    def register_many(self, rooms: Dict[str, Dict[str, Any]]):
        by_div: Dict[str, List[str]] = {}
        for rid, meta in rooms.items():
            div = (meta or {}).get("division", "Other")
            self.register_room(rid, div)
            by_div.setdefault(div, []).append(rid)
        # lateral mesh within division
        for div, ids in by_div.items():
            for i, a in enumerate(ids):
                for b in ids[i + 1 : i + 3]:  # limited lateral fanout
                    self._add_edge(a, b, "lateral", 0.4)
                    self._add_edge(b, a, "lateral", 0.4)

    def route_to_boardroom(self, room_id: str, event: str, payload: Optional[dict] = None) -> dict:
        msg = {
            "ts": _ts(),
            "from": room_id,
            "to": self.BOARDROOM,
            "kind": "uplink",
            "event": event,
            "payload": payload or {},
        }
        self.traffic.append(msg)
        if len(self.traffic) > 5000:
            self.traffic = self.traffic[-5000:]
        return msg

    def broadcast_from_boardroom(self, event: str, payload: Optional[dict] = None, room_ids: Optional[List[str]] = None) -> List[dict]:
        targets = room_ids or [n for n in self.nodes if n != self.BOARDROOM]
        out = []
        for rid in targets:
            msg = {
                "ts": _ts(),
                "from": self.BOARDROOM,
                "to": rid,
                "kind": "downlink",
                "event": event,
                "payload": payload or {},
            }
            self.traffic.append(msg)
            out.append(msg)
        if len(self.traffic) > 5000:
            self.traffic = self.traffic[-5000:]
        return out

    def neighbors(self, room_id: str) -> Dict[str, List[str]]:
        up = [e.to_id for e in self.edges if e.from_id == room_id and e.kind == "uplink"]
        down = [e.to_id for e in self.edges if e.from_id == room_id and e.kind == "downlink"]
        lat = [e.to_id for e in self.edges if e.from_id == room_id and e.kind == "lateral"]
        return {"uplink": up, "downlink": down, "lateral": lat}

    def status(self) -> Dict[str, Any]:
        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "traffic": len(self.traffic),
            "boardroom_links": sum(1 for e in self.edges if self.BOARDROOM in (e.from_id, e.to_id)),
        }
