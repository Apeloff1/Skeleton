"""
Skeleton Galaxy — Distributed node coordination and federation

Provides:
- GalaxyNode: A single node in the distributed galaxy
- FederationMesh: Cross-node communication and consensus
- NodeRegistry: Track and discover nodes in the galaxy
"""

from __future__ import annotations

import hashlib
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set

from skeleton.kernel.events import DomainEvent, EventBus


@dataclass
class NodeIdentity:
    """Identity of a galaxy node."""
    node_id: str
    address: str
    region: str
    capabilities: Set[str] = field(default_factory=set)
    metadata: Dict[str, Any] = field(default_factory=dict)
    last_heartbeat: float = field(default_factory=time.time)

    def is_alive(self, timeout: float = 30.0) -> bool:
        return time.time() - self.last_heartbeat < timeout


class NodeRegistry:
    """Track and discover nodes in the galaxy."""

    def __init__(self, bus: Optional[EventBus] = None):
        self._nodes: Dict[str, NodeIdentity] = {}
        self._bus = bus
        self._stats = {"registered": 0, "expired": 0, "heartbeats": 0}

    def register(self, node_id: str, address: str, region: str = "default", capabilities: Optional[Set[str]] = None) -> NodeIdentity:
        """Register a new node in the galaxy."""
        node = NodeIdentity(
            node_id=node_id,
            address=address,
            region=region,
            capabilities=capabilities or set(),
        )
        self._nodes[node_id] = node
        self._stats["registered"] += 1
        
        if self._bus:
            self._bus.emit("galaxy.node.registered", {
                "node_id": node_id,
                "address": address,
                "region": region,
            })
        
        return node

    def heartbeat(self, node_id: str) -> bool:
        """Update node heartbeat."""
        if node_id not in self._nodes:
            return False
        self._nodes[node_id].last_heartbeat = time.time()
        self._stats["heartbeats"] += 1
        return True

    def discover(self, capability: Optional[str] = None, region: Optional[str] = None) -> List[NodeIdentity]:
        """Discover nodes matching criteria."""
        results = []
        for node in self._nodes.values():
            if not node.is_alive():
                continue
            if capability and capability not in node.capabilities:
                continue
            if region and node.region != region:
                continue
            results.append(node)
        return results

    def remove_expired(self, timeout: float = 60.0) -> int:
        """Remove nodes that haven't heartbeated within timeout."""
        expired = [nid for nid, node in self._nodes.items() if not node.is_alive(timeout)]
        for nid in expired:
            del self._nodes[nid]
            self._stats["expired"] += 1
        return len(expired)

    def stats(self) -> Dict[str, Any]:
        alive = sum(1 for n in self._nodes.values() if n.is_alive())
        return {
            **self._stats,
            "total": len(self._nodes),
            "alive": alive,
        }


class FederationMesh:
    """Cross-node communication and consensus formation."""

    def __init__(self, registry: NodeRegistry, bus: Optional[EventBus] = None):
        self._registry = registry
        self._bus = bus
        self._outbox: Dict[str, List[Dict[str, Any]]] = {}  # node_id -> messages
        self._inbox: Dict[str, List[Dict[str, Any]]] = {}
        self._consensus_log: List[Dict[str, Any]] = []

    def send(self, target_node: str, message: Dict[str, Any]) -> bool:
        """Send a message to a target node."""
        if target_node not in self._registry._nodes:
            return False
        
        envelope = {
            "from": "local",
            "to": target_node,
            "timestamp": time.time(),
            "payload": message,
            "message_id": str(uuid.uuid4())[:8],
        }
        self._outbox.setdefault(target_node, []).append(envelope)
        
        if self._bus:
            self._bus.emit("galaxy.message.sent", {
                "target": target_node,
                "message_id": envelope["message_id"],
            })
        
        return True

    def broadcast(self, message: Dict[str, Any], filter_capability: Optional[str] = None) -> int:
        """Broadcast to all capable nodes."""
        targets = self._registry.discover(capability=filter_capability)
        sent = 0
        for node in targets:
            if self.send(node.node_id, message):
                sent += 1
        return sent

    def propose(self, topic: str, value: Any) -> str:
        """Propose a value for consensus."""
        proposal_id = str(uuid.uuid4())[:8]
        proposal = {
            "proposal_id": proposal_id,
            "topic": topic,
            "value": value,
            "timestamp": time.time(),
            "votes": {},
        }
        self._consensus_log.append(proposal)
        
        # Broadcast proposal
        self.broadcast({
            "type": "proposal",
            "proposal_id": proposal_id,
            "topic": topic,
            "value": value,
        })
        
        return proposal_id

    def vote(self, proposal_id: str, node_id: str, accept: bool) -> Optional[Dict[str, Any]]:
        """Cast a vote on a proposal."""
        for proposal in self._consensus_log:
            if proposal["proposal_id"] == proposal_id:
                proposal["votes"][node_id] = accept
                
                # Check if consensus reached
                alive_nodes = len(self._registry.discover())
                votes = proposal["votes"]
                if len(votes) >= alive_nodes * 0.5:  # Simple majority
                    accepted = sum(votes.values()) > len(votes) / 2
                    proposal["status"] = "accepted" if accepted else "rejected"
                    proposal["final_votes"] = dict(votes)
                    
                    if self._bus:
                        self._bus.emit("galaxy.consensus.reached", {
                            "proposal_id": proposal_id,
                            "accepted": accepted,
                            "votes": len(votes),
                        })
                    
                    return proposal
        
        return None

    def stats(self) -> Dict[str, Any]:
        return {
            "outbox_messages": sum(len(m) for m in self._outbox.values()),
            "inbox_messages": sum(len(m) for m in self._inbox.values()),
            "consensus_proposals": len(self._consensus_log),
            "resolved": sum(1 for p in self._consensus_log if "status" in p),
        }


class GalaxyNode:
    """A single node in the distributed Skeleton galaxy."""

    def __init__(self, node_id: Optional[str] = None, address: str = "localhost", region: str = "default", bus: Optional[EventBus] = None):
        self.node_id = node_id or str(uuid.uuid4())[:8]
        self.address = address
        self.region = region
        self._bus = bus
        self._registry = NodeRegistry(bus=bus)
        self._mesh = FederationMesh(self._registry, bus=bus)
        self._capabilities: Set[str] = set()
        self._started = False

    def add_capability(self, capability: str) -> None:
        self._capabilities.add(capability)

    def start(self) -> None:
        """Start the galaxy node."""
        self._registry.register(
            self.node_id,
            self.address,
            self.region,
            capabilities=self._capabilities,
        )
        self._started = True
        
        if self._bus:
            self._bus.emit("galaxy.node.started", {
                "node_id": self.node_id,
                "address": self.address,
                "region": self.region,
            })

    def heartbeat(self) -> None:
        """Send heartbeat to maintain node liveness."""
        self._registry.heartbeat(self.node_id)

    def join_galaxy(self, seed_nodes: List[str]) -> None:
        """Join an existing galaxy via seed nodes."""
        for seed in seed_nodes:
            self._mesh.send(seed, {
                "type": "join_request",
                "node_id": self.node_id,
                "address": self.address,
                "region": self.region,
                "capabilities": list(self._capabilities),
            })

    def propose_consensus(self, topic: str, value: Any) -> str:
        """Propose a value for galaxy-wide consensus."""
        return self._mesh.propose(topic, value)

    def stats(self) -> Dict[str, Any]:
        return {
            "node_id": self.node_id,
            "region": self.region,
            "capabilities": len(self._capabilities),
            "started": self._started,
            "registry": self._registry.stats(),
            "mesh": self._mesh.stats(),
        }
