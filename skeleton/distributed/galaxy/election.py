"""
Skeleton Galaxy — Leader election

Elects a coordinator for the fleet on top of the consensus primitive:

    Any node may call an election → candidates are the live electorate,
    ordered deterministically (highest capability count, then node_id)
    → the top candidate is proposed as leader → majority vote →
    outcome broadcast installs the leader fleet-wide

The leader's roles:
- offer_remote routes through the leader (it coordinates assignment)
- KAG gossip can be leader-initiated for fleet-wide sync ticks
- Heartbeat monitoring: if the leader goes silent past TTL, any node
  may call a new election (Bully-style)

Provides:
- LeaderElection: election lifecycle bound to node + transport + consensus
- LeadershipState: current leader, term, staleness
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class LeadershipState:
    """Current leadership view of a node."""
    leader_id: str = ""
    term: int = 0
    elected_at: float = 0.0

    LEADER_TTL = 30.0  # seconds without heartbeat before re-election allowed

    def is_leader(self, node_id: str) -> bool:
        return bool(self.leader_id) and self.leader_id == node_id

    def is_stale(self) -> bool:
        if not self.leader_id:
            return True
        return time.time() - self.elected_at > self.LEADER_TTL

    def to_dict(self) -> Dict[str, Any]:
        return {
            "leader_id": self.leader_id,
            "term": self.term,
            "age_seconds": round(time.time() - self.elected_at, 1) if self.elected_at else None,
            "stale": self.is_stale(),
        }


class LeaderElection:
    """Bully-style leader election over the consensus engine.

    Deterministic candidacy: rank = (capability_count, node_id) — the
    most capable node with the lexicographically highest id wins ties.
    Every node computes the same candidate set from the shared registry,
    so one proposal suffices to install the winner fleet-wide.
    """

    def __init__(self, node: Any, transport: Any, consensus: Any, bus: Optional[Any] = None):
        self._node = node
        self._transport = transport
        self._consensus = consensus
        self._bus = bus
        self.state = LeadershipState()
        self._stats = {"elections_called": 0, "elections_won": 0, "elections_lost": 0,
                       "heartbeats_sent": 0}

        transport.on("leader.install", self._on_install)
        transport.on("leader.heartbeat", self._on_heartbeat)

    # --- Candidacy -------------------------------------------------------

    def candidates(self) -> List[str]:
        """Deterministically ranked candidate list (best first)."""
        entries = [(len(self._node._capabilities), self._node.node_id)]
        for peer in self._node._registry.discover():
            entries.append((len(peer.capabilities), peer.node_id))
        entries.sort(key=lambda e: (e[0], e[1]), reverse=True)
        return [node_id for _, node_id in entries]

    def top_candidate(self) -> str:
        ranked = self.candidates()
        return ranked[0] if ranked else self._node.node_id

    # --- Election lifecycle ----------------------------------------------

    def call_election(self, wait: bool = True, timeout: float = 5.0) -> Optional[str]:
        """Propose the top candidate as leader via consensus."""
        self._stats["elections_called"] += 1
        candidate = self.top_candidate()
        new_term = self.state.term + 1

        proposal = self._consensus.propose(
            "leader.elect",
            {"candidate": candidate, "term": new_term},
            wait=wait,
            timeout=timeout,
        )

        if proposal.status == "accepted":
            self._install(candidate, new_term)
            self._broadcast_install(candidate, new_term)
            return candidate
        return None

    def _install(self, leader_id: str, term: int) -> None:
        was_self = self.state.is_leader(self._node.node_id)
        self.state = LeadershipState(leader_id=leader_id, term=term, elected_at=time.time())
        is_self = self.state.is_leader(self._node.node_id)
        if is_self and not was_self:
            self._stats["elections_won"] += 1
        elif not is_self:
            self._stats["elections_lost"] += 1
        if self._bus:
            self._bus.emit("galaxy.leader.installed", {
                "leader_id": leader_id,
                "term": term,
                "is_self": is_self,
            })

    def _broadcast_install(self, leader_id: str, term: int) -> None:
        for peer in self._node._registry.discover():
            self._transport.send(peer.address, {
                "type": "leader.install",
                "leader_id": leader_id,
                "term": term,
            })

    # --- Wire handlers ---------------------------------------------------

    def _on_install(self, payload: Dict[str, Any]) -> None:
        """Accept an install for a newer term."""
        term = int(payload.get("term", 0))
        if term >= self.state.term:
            self._install(payload["leader_id"], term)

    def _on_heartbeat(self, payload: Dict[str, Any]) -> None:
        """Leader liveness: refresh staleness clock if from current leader."""
        if payload.get("leader_id") == self.state.leader_id:
            self.state.elected_at = time.time()

    # --- Leader duties ----------------------------------------------------

    def heartbeat_fleet(self) -> int:
        """Leader-only: ping all peers to hold the TTL. Returns peer count."""
        if not self.state.is_leader(self._node.node_id):
            return 0
        peers = self._node._registry.discover()
        for peer in peers:
            self._transport.send(peer.address, {
                "type": "leader.heartbeat",
                "leader_id": self._node.node_id,
                "term": self.state.term,
            })
            self._stats["heartbeats_sent"] += 1
        return len(peers)

    def maybe_reelect(self) -> Optional[str]:
        """If leadership is stale, call a fresh election."""
        if self.state.is_stale():
            return self.call_election()
        return self.state.leader_id

    # --- Queries ----------------------------------------------------------

    def leader(self) -> Optional[str]:
        """Current leader, or None if unknown/stale."""
        return None if self.state.is_stale() else self.state.leader_id

    def is_leader(self) -> bool:
        return self.state.is_leader(self._node.node_id) and not self.state.is_stale()

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "state": self.state.to_dict()}
