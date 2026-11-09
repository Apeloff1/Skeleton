"""
Skeleton Foundation — Merkle DAG Content-Addressed Store

The deepest storage primitive: every object addressed by the hash of
its own content. Immutable, deduplicated, tamper-evident, and linked
— children name their parents by hash, so the entire history of any
artifact is a cryptographically-verifiable chain.

Semantics:
- put(obj) → hash. Same content → same hash → stored once, forever.
  The address IS the integrity proof: read back, rehash, compare.
- Nodes may link to other nodes by hash ("links": [hash, ...]),
  forming a DAG. A root hash therefore commits to its entire
  ancestry — change any byte anywhere upstream and every hash
  downstream changes.
- verify(hash) walks the object and its links, rehashing each node —
  full-structure integrity in O(nodes), not O(bytes-inspected).
- Garbage: nothing is deleted. History is the point. (Optional
  ref-counted GC surface included for embedded profiles.)

Everything else in the system — KAG triples, blueprints, snapshots,
chain blocks — can be rooted here: one store, every artifact
verifiable, every provenance chain provable.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


def canonical(obj: Any) -> bytes:
    """Deterministic serialization: sorted keys, no whitespace variance."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, default=str).encode("utf-8")


def content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class Node:
    """One immutable DAG node."""
    hash: str
    kind: str
    payload: Any
    links: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {"hash": self.hash, "kind": self.kind, "payload": self.payload,
                "links": self.links, "created_at": self.created_at}


class MerkleDAG:
    """Content-addressed immutable store with link-based provenance."""

    def __init__(self):
        self._nodes: Dict[str, Node] = {}
        self._refs: Dict[str, int] = {}  # ref counting for optional GC
        self._stats = {"puts": 0, "deduped": 0, "gets": 0, "verified": 0}

    def put(self, payload: Any, kind: str = "object",
            links: Optional[List[str]] = None) -> str:
        """Store content; return its hash. Idempotent by construction."""
        links = list(links or [])
        body = {"kind": kind, "payload": payload, "links": links}
        h = content_hash(canonical(body))
        if h in self._nodes:
            self._stats["deduped"] += 1
            return h
        self._nodes[h] = Node(hash=h, kind=kind, payload=payload, links=links)
        for link in links:
            self._refs[link] = self._refs.get(link, 0) + 1
        self._stats["puts"] += 1
        return h

    def get(self, h: str) -> Optional[Node]:
        self._stats["gets"] += 1
        return self._nodes.get(h)

    def verify(self, h: str) -> bool:
        """Rehash a node and walk its links; any tamper fails."""
        self._stats["verified"] += 1
        node = self._nodes.get(h)
        if node is None:
            return False
        body = {"kind": node.kind, "payload": node.payload, "links": node.links}
        if content_hash(canonical(body)) != h:
            return False
        for link in node.links:
            if link not in self._nodes:
                return False
            if not self.verify(link):
                return False
        return True

    def ancestry(self, h: str, max_depth: int = 64) -> List[str]:
        """Hashes reachable from h, breadth-first (provenance chain)."""
        out: List[str] = []
        seen = {h}
        queue = [h]
        while queue and len(out) < max_depth:
            cur = queue.pop(0)
            out.append(cur)
            node = self._nodes.get(cur)
            if node:
                for link in node.links:
                    if link not in seen:
                        seen.add(link)
                        queue.append(link)
        return out

    def diff(self, a: str, b: str) -> Dict[str, Any]:
        """Structural diff: which nodes are unique to each side."""
        set_a = set(self.ancestry(a))
        set_b = set(self.ancestry(b))
        return {
            "only_a": sorted(set_a - set_b),
            "only_b": sorted(set_b - set_a),
            "shared": len(set_a & set_b),
        }

    def gc_sweep(self, roots: List[str]) -> int:
        """Optional ref-counted GC for embedded profiles: drop nodes not
        reachable from the given roots. History-keeping default is OFF."""
        reachable = set()
        for root in roots:
            reachable.update(self.ancestry(root))
        doomed = [h for h in self._nodes if h not in reachable]
        for h in doomed:
            del self._nodes[h]
        return len(doomed)

    def stats(self) -> Dict[str, Any]:
        return {**self._stats, "nodes": len(self._nodes)}


# --- Domain adapters: root system artifacts in the DAG -------------------

class DAGAdapter:
    """Roots KAG triples, blueprints, and snapshots into the DAG."""

    def __init__(self, dag: MerkleDAG):
        self.dag = dag

    def store_triples(self, triples: List[Any], parent: Optional[str] = None) -> str:
        """Append a KAG batch as a linked node (temporal provenance)."""
        payload = [{"s": getattr(t, "subject", t[0] if len(t) > 0 else ""),
                    "p": getattr(t, "predicate", t[1] if len(t) > 1 else ""),
                    "o": getattr(t, "obj", t[2] if len(t) > 2 else "")}
                   for t in triples]
        return self.dag.put(payload, kind="kag.batch",
                            links=[parent] if parent else [])

    def store_blueprint(self, blueprint: Any, parent: Optional[str] = None) -> str:
        payload = blueprint.to_dict() if hasattr(blueprint, "to_dict") else dict(blueprint)
        return self.dag.put(payload, kind="forge.blueprint",
                            links=[parent] if parent else [])

    def store_snapshot(self, name: str, data: Dict[str, Any],
                       parent: Optional[str] = None) -> str:
        return self.dag.put({"name": name, "data": data}, kind="snapshot",
                            links=[parent] if parent else [])
