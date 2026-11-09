"""
Skeleton Galaxy — Leader-coordinated fleet operations

The elected leader coordinates two fleet-wide duties:

1. Load-aware task routing: offers flow through the leader, which
   tracks per-node load (accepted tasks minus completions) and
   assigns each offer to the least-loaded capable peer.
2. Periodic KAG sync ticks: the leader initiates fleet-wide gossip
   on an interval so knowledge converges without manual sync_now()
   calls.

Wire messages:
- fleet.assign    {task_id, specialisation, description, origin, assigned_to}
- fleet.sync_tick {leader_id, term}

Provides:
- FleetCoordinator: leader-side coordination logic
- LoadLedger: per-node load accounting
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LoadLedger:
    """Per-node load accounting for leader-side routing."""
    loads: Dict[str, int] = field(default_factory=dict)

    def record_accept(self, node_id: str) -> None:
        self.loads[node_id] = self.loads.get(node_id, 0) + 1

    def record_complete(self, node_id: str) -> None:
        self.loads[node_id] = max(0, self.loads.get(node_id, 0) - 1)

    def least_loaded(self, candidates: List[str]) -> Optional[str]:
        """Pick the least-loaded candidate (ties → lexicographic order)."""
        if not candidates:
            return None
        return min(candidates, key=lambda n: (self.loads.get(n, 0), n))

    def snapshot(self) -> Dict[str, int]:
        return dict(self.loads)


class FleetCoordinator:
    """Leader-side coordination: load-aware routing + sync ticks.

    Runs on every node but only acts when `election.is_leader()` is
    true; followers forward offers to the leader and react to
    assignments and sync ticks.
    """

    DEFAULT_TICK_INTERVAL = 60.0  # seconds between leader sync ticks

    def __init__(self, node: Any, transport: Any, election: Any, kag_sync: Optional[Any] = None,
                 bus: Optional[Any] = None, tick_interval: float = DEFAULT_TICK_INTERVAL):
        self._node = node
        self._transport = transport
        self._election = election
        self._kag_sync = kag_sync
        self._bus = bus
        self.tick_interval = tick_interval
        self.ledger = LoadLedger()
        self._last_tick = 0.0
        self._stats = {"assignments": 0, "forwards": 0, "ticks": 0, "tick_gossips": 0}

        transport.on("fleet.assign", self._on_assign)
        transport.on("fleet.sync_tick", self._on_sync_tick)

    # --- Leader duties ----------------------------------------------------

    def assign(self, specialisation: str, candidates: List[Any], task_id: str,
               description: str = "", origin: str = "") -> Optional[Any]:
        """Leader-only: pick the least-loaded capable candidate.

        `candidates` is a list of NodeIdentity-like objects with
        node_id and address. Returns the chosen candidate (or None).
        """
        if not self._election.is_leader():
            return None
        chosen_id = self.ledger.least_loaded([c.node_id for c in candidates])
        if chosen_id is None:
            return None
        chosen = next(c for c in candidates if c.node_id == chosen_id)
        self.ledger.record_accept(chosen_id)
        self._stats["assignments"] += 1

        # Notify the origin node of the assignment decision
        if origin and origin != self._node.node_id:
            origin_node = self._node._registry._nodes.get(origin)
            if origin_node is not None:
                self._transport.send(origin_node.address, {
                    "type": "fleet.assign",
                    "task_id": task_id,
                    "specialisation": specialisation,
                    "description": description,
                    "assigned_to": chosen_id,
                })

        if self._bus:
            self._bus.emit("galaxy.fleet.assigned", {
                "task_id": task_id,
                "specialisation": specialisation,
                "assigned_to": chosen_id,
                "loads": self.ledger.snapshot(),
            })
        return chosen

    def record_completion(self, node_id: str) -> None:
        self.ledger.record_complete(node_id)

    def tick(self, force: bool = False) -> bool:
        """Leader-only: fire a fleet-wide sync tick if the interval passed."""
        if not self._election.is_leader():
            return False
        now = time.time()
        if not force and now - self._last_tick < self.tick_interval:
            return False
        self._last_tick = now
        self._stats["ticks"] += 1

        peers = self._node._registry.discover()
        for peer in peers:
            self._transport.send(peer.address, {
                "type": "fleet.sync_tick",
                "leader_id": self._node.node_id,
                "term": self._election.state.term,
            })

        # Leader gossips its own KAG digest as part of the tick
        if self._kag_sync is not None:
            self._stats["tick_gossips"] += self._kag_sync.gossip()

        if self._bus:
            self._bus.emit("galaxy.fleet.tick", {
                "leader_id": self._node.node_id,
                "peers": len(peers),
                "tick": self._stats["ticks"],
            })
        return True

    def forward_to_leader(self, payload: Dict[str, Any]) -> bool:
        """Follower: forward a coordination request to the current leader."""
        leader_id = self._election.leader()
        if not leader_id or leader_id == self._node.node_id:
            return False
        leader_node = self._node._registry._nodes.get(leader_id)
        if leader_node is None:
            return False
        self._stats["forwards"] += 1
        return self._transport.send(leader_node.address, payload)

    # --- Wire handlers ----------------------------------------------------

    def _on_assign(self, payload: Dict[str, Any]) -> None:
        """Follower: leader told us who got the assignment; record load."""
        assigned = payload.get("assigned_to")
        if assigned:
            self.ledger.record_accept(assigned)

    def _on_sync_tick(self, payload: Dict[str, Any]) -> None:
        """Follower: leader ticked — gossip our KAG digest back."""
        if payload.get("leader_id") != self._election.leader():
            return
        if self._kag_sync is not None:
            self._stats["tick_gossips"] += self._kag_sync.gossip()

    # --- Queries ----------------------------------------------------------

    def stats(self) -> Dict[str, Any]:
        return {
            **self._stats,
            "is_leader": self._election.is_leader(),
            "loads": self.ledger.snapshot(),
            "last_tick_age": round(time.time() - self._last_tick, 1) if self._last_tick else None,
        }
