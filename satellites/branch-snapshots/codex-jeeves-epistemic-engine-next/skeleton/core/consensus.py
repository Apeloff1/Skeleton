"""Consensus — leader election with terms and heartbeats.

Raft-lite leader election for Skeleton subsystem replicas. Nodes
campaign with monotonic terms, peers vote once per term, heartbeats
maintain leadership, and a stale leader steps down when it sees a
higher term. Deterministic and transport-agnostic — callers wire
message passing to their own transport.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set


@dataclass
class Node:
    node_id: str
    term: int = 0
    voted_for: Optional[str] = None
    role: str = "follower"          # follower | candidate | leader
    last_heartbeat_ns: int = 0
    votes_received: Set[str] = field(default_factory=set)


class ConsensusCluster:
    """Multi-node leader election with terms and heartbeats."""

    def __init__(self, heartbeat_timeout_s: float = 5.0):
        self._nodes: Dict[str, Node] = {}
        self.heartbeat_timeout_s = heartbeat_timeout_s
        self._election_count = 0

    def add_node(self, node_id: str) -> Node:
        node = Node(node_id=node_id, last_heartbeat_ns=time.time_ns())
        self._nodes[node_id] = node
        return node

    def remove_node(self, node_id: str) -> bool:
        return self._nodes.pop(node_id, None) is not None

    def majority(self) -> int:
        return len(self._nodes) // 2 + 1

    def start_election(self, candidate_id: str) -> Dict[str, Any]:
        candidate = self._nodes[candidate_id]
        candidate.term += 1
        candidate.role = "candidate"
        candidate.voted_for = candidate_id
        candidate.votes_received = {candidate_id}
        self._election_count += 1
        return {"term": candidate.term, "candidate": candidate_id}

    def request_vote(self, candidate_id: str, term: int, voter_id: str) -> bool:
        voter = self._nodes.get(voter_id)
        candidate = self._nodes.get(candidate_id)
        if not voter or not candidate:
            return False
        if term < voter.term:
            return False
        if term > voter.term:
            voter.term = term
            voter.voted_for = None
            voter.role = "follower"
        if voter.voted_for is None or voter.voted_for == candidate_id:
            voter.voted_for = candidate_id
            candidate.votes_received.add(voter_id)
            if len(candidate.votes_received) >= self.majority():
                candidate.role = "leader"
                candidate.last_heartbeat_ns = time.time_ns()
            return True
        return False

    def heartbeat(self, leader_id: str, term: int) -> Dict[str, Any]:
        leader = self._nodes.get(leader_id)
        if not leader or leader.role != "leader":
            return {"accepted": False, "reason": "not leader"}
        acknowledged = 0
        for node in self._nodes.values():
            if node.node_id == leader_id:
                continue
            if term >= node.term:
                node.term = term
                node.role = "follower"
                node.last_heartbeat_ns = time.time_ns()
                acknowledged += 1
        leader.last_heartbeat_ns = time.time_ns()
        return {"accepted": True, "acknowledged": acknowledged}

    def check_leader_alive(self) -> bool:
        leader = self.leader()
        if not leader:
            return False
        return (time.time_ns() - leader.last_heartbeat_ns) / 1e9 < self.heartbeat_timeout_s

    def leader(self) -> Optional[Node]:
        for node in self._nodes.values():
            if node.role == "leader":
                return node
        return None

    def step_down(self, node_id: str, seen_term: int) -> bool:
        node = self._nodes.get(node_id)
        if node and seen_term > node.term:
            node.term = seen_term
            node.role = "follower"
            node.voted_for = None
            return True
        return False

    def card(self) -> Dict[str, Any]:
        leader = self.leader()
        return {
            "kind": "consensus-card",
            "nodes": {n: {"role": v.role, "term": v.term, "voted_for": v.voted_for} for n, v in self._nodes.items()},
            "leader": leader.node_id if leader else None,
            "leader_alive": self.check_leader_alive(),
            "term": max((n.term for n in self._nodes.values()), default=0),
            "elections": self._election_count,
            "majority_needed": self.majority(),
        }
