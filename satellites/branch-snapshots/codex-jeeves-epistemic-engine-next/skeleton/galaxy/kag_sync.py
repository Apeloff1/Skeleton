"""
Skeleton Galaxy — Federated KAG sync

Replicates knowledge-graph triples between galaxy nodes over the live
transport, so knowledge ingested on one node propagates to its peers.

Design:
- Anti-entropy, not event streaming: nodes periodically gossip digests
  of their triple sets and pull the triples they're missing. Eventual
  consistency with bounded message volume.
- Lamport-style conflict freedom: triples are immutable facts, so
  union is the merge — no conflicts to resolve.
- Optional consensus gating: when a ConsensusEngine is attached,
  large batches (> gossip_threshold new triples) are proposed for a
  vote before merging — peers can veto floods of low-quality facts.

Wire messages:
- kag.digest   {node_id, count, hashes[]}
- kag.request  {node_id, want[]}
- kag.triples  {node_id, triples[[s,p,o], ...]}
"""

from __future__ import annotations

import hashlib
import time
from typing import Any, Callable, Dict, List, Optional, Set, Tuple


def _triple_hash(triple: Tuple[str, str, str]) -> str:
    s, p, o = triple
    return hashlib.blake2b(f"{s}|{p}|{o}".encode(), digest_size=8).hexdigest()


class KAGSync:
    """Anti-entropy replication for a KAGRetriever's knowledge graph."""

    def __init__(
        self,
        kag: Any,
        node: Any,
        transport: Any,
        consensus: Optional[Any] = None,
        gossip_threshold: int = 50,
        bus: Optional[Any] = None,
    ):
        self._kag = kag
        self._node = node
        self._transport = transport
        self._consensus = consensus
        self._gossip_threshold = gossip_threshold
        self._bus = bus
        self._seen: Set[str] = set()
        self._stats = {"digests_sent": 0, "digests_received": 0, "triples_sent": 0,
                       "triples_received": 0, "merges": 0, "consensus_gated": 0}
        self._index_local()

        transport.on("kag.digest", self._on_digest)
        transport.on("kag.request", self._on_request)
        transport.on("kag.triples", self._on_triples)

    # --- Local index ----------------------------------------------------

    def _index_local(self) -> None:
        """Refresh the seen-hash index from the local graph."""
        self._seen = {_triple_hash((t.subject, t.predicate, t.obj)) for t in self._kag.graph._triples}

    def digest(self) -> Dict[str, Any]:
        """Local digest: count + hashes, for gossip."""
        self._index_local()
        return {
            "node_id": self._node.node_id,
            "count": len(self._seen),
            "hashes": sorted(self._seen),
        }

    def gossip(self) -> int:
        """Send our digest to every known peer. Returns peer count."""
        peers = self._node._registry.discover()
        payload = {"type": "kag.digest", **self.digest()}
        for peer in peers:
            self._transport.send(peer.address, payload)
            self._stats["digests_sent"] += 1
        return len(peers)

    # --- Wire handlers --------------------------------------------------

    def _on_digest(self, payload: Dict[str, Any]) -> None:
        """Peer sent their digest: request the triples we lack."""
        self._stats["digests_received"] += 1
        self._index_local()
        missing = [h for h in payload.get("hashes", []) if h not in self._seen]
        if not missing:
            return
        sender = self._node._registry._nodes.get(payload.get("node_id"))
        if sender is not None:
            self._transport.send(sender.address, {
                "type": "kag.request",
                "node_id": self._node.node_id,
                "want": missing,
            })

    def _on_request(self, payload: Dict[str, Any]) -> None:
        """Peer wants specific triples by hash: send them."""
        want = set(payload.get("want", []))
        matches = [
            (t.subject, t.predicate, t.obj)
            for t in self._kag.graph._triples
            if _triple_hash((t.subject, t.predicate, t.obj)) in want
        ]
        if not matches:
            return
        requester = self._node._registry._nodes.get(payload.get("node_id"))
        if requester is not None:
            self._transport.send(requester.address, {
                "type": "kag.triples",
                "node_id": self._node.node_id,
                "triples": [list(m) for m in matches],
            })
            self._stats["triples_sent"] += len(matches)

    def _on_triples(self, payload: Dict[str, Any]) -> None:
        """Incoming triples: merge into the local graph (union — no conflicts)."""
        incoming = [tuple(t) for t in payload.get("triples", [])]
        if not incoming:
            return

        # Consensus gate for large batches
        if self._consensus is not None and len(incoming) > self._gossip_threshold:
            self._stats["consensus_gated"] += 1
            proposal = self._consensus.propose(
                "kag.sync.batch",
                {"from": payload.get("node_id"), "count": len(incoming)},
                wait=True, timeout=5.0,
            )
            if proposal.status != "accepted":
                return

        merged = 0
        for s, p, o in incoming:
            h = _triple_hash((s, p, o))
            if h not in self._seen:
                self._kag.graph.add(s, p, o)
                self._seen.add(h)
                merged += 1

        if merged:
            self._stats["triples_received"] += merged
            self._stats["merges"] += 1
            if self._bus:
                self._bus.emit("galaxy.kag.synced", {
                    "from": payload.get("node_id"),
                    "merged": merged,
                    "total": len(self._seen),
                })

    # --- Convenience ----------------------------------------------------

    def sync_now(self) -> Dict[str, Any]:
        """One-shot sync: gossip our digest; peers will request what they lack."""
        peers = self.gossip()
        return {"peers_notified": peers, "local_triples": len(self._seen)}

    def push_all(self) -> int:
        """Push the full local graph to every peer (bootstrap a new node)."""
        peers = self._node._registry.discover()
        triples = [[t.subject, t.predicate, t.obj] for t in self._kag.graph._triples]
        if not triples:
            return 0
        for peer in peers:
            self._transport.send(peer.address, {
                "type": "kag.triples",
                "node_id": self._node.node_id,
                "triples": triples,
            })
            self._stats["triples_sent"] += len(triples)
        return len(peers) * len(triples)

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "local_triples": len(self._seen)}
