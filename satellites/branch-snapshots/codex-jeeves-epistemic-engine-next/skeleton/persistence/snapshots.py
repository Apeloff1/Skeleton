"""
Skeleton Persistence — Snapshot and restore for memory planes

Provides:
- SnapshotStore: File-based snapshot registry (.skeleton/snapshots/)
- Plane serializers: VectorStore, MAGStore, KnowledgeGraph, matrices
- restore_genesis_state / snapshot_genesis_state: whole-system capture

Snapshots are plain JSON so they're inspectable and diffable.
The layer is opt-in: nothing writes to disk unless asked.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


DEFAULT_ROOT = Path(".skeleton/snapshots")


class SnapshotStore:
    """File-based snapshot registry."""

    def __init__(self, root: Optional[Path] = None):
        self.root = Path(root) if root else DEFAULT_ROOT
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, name: str, data: Dict[str, Any]) -> Path:
        """Write a snapshot file, returns its path."""
        path = self.root / f"{name}.json"
        payload = {"name": name, "saved_at": time.time(), "data": data}
        path.write_text(json.dumps(payload, indent=2, default=str))
        return path

    def load(self, name: str) -> Optional[Dict[str, Any]]:
        """Load a snapshot's data payload, or None if missing."""
        path = self.root / f"{name}.json"
        if not path.exists():
            return None
        try:
            return json.loads(path.read_text())["data"]
        except Exception:
            return None

    def list(self) -> List[Dict[str, Any]]:
        """List available snapshots."""
        out = []
        for path in sorted(self.root.glob("*.json")):
            try:
                payload = json.loads(path.read_text())
                out.append({"name": payload["name"], "saved_at": payload["saved_at"]})
            except Exception:
                continue
        return out

    def delete(self, name: str) -> bool:
        path = self.root / f"{name}.json"
        if path.exists():
            path.unlink()
            return True
        return False


# --- Plane serializers -------------------------------------------------

def serialize_vector_store(store: Any) -> Dict[str, Any]:
    """Serialize a VectorStore's documents (vectors recomputed on load)."""
    return {
        "kind": "vector_store",
        "documents": [
            {"chunk_id": e.chunk.chunk_id, "text": e.chunk.text, "metadata": e.chunk.metadata}
            for e in store._entries.values()
        ],
    }


def restore_vector_store(data: Dict[str, Any], store: Any) -> int:
    """Reload documents into a VectorStore (re-embeds each text)."""
    from skeleton.memory.core import Chunk
    count = 0
    for doc in data.get("documents", []):
        store.add(Chunk(text=doc["text"], chunk_id=doc["chunk_id"], metadata=doc.get("metadata", {})))
        count += 1
    return count


def serialize_mag(mag: Any) -> Dict[str, Any]:
    return {
        "kind": "mag_store",
        "agent_id": mag.agent_id,
        "episodes": mag._episodes,
    }


def restore_mag(data: Dict[str, Any], mag: Any) -> int:
    episodes = data.get("episodes", {})
    for eid, ep in episodes.items():
        mag._episodes[eid] = ep
        for tag in ep.get("tags", []):
            mag._tag_index.setdefault(tag, set()).add(eid)
    return len(episodes)


def serialize_graph(graph: Any) -> Dict[str, Any]:
    return {
        "kind": "knowledge_graph",
        "triples": [list(t) for t in sorted(graph._triples, key=str)],
    }


def restore_graph(data: Dict[str, Any], graph: Any) -> int:
    count = 0
    for s, p, o in data.get("triples", []):
        graph.add(s, p, o)
        count += 1
    return count


def serialize_matrices(jeeves: Any) -> Dict[str, Any]:
    """Serialize Jeeves matrices (SAM edges, CLOM records, KREM cells)."""
    return {
        "kind": "jeeves_matrices",
        "sam": {a: dict(es) for a, es in jeeves.sam._edges.items()},
        "clom": {
            intent: [
                {"success": r.success, "latency_ms": r.latency_ms, "timestamp": r.timestamp}
                for r in records
            ]
            for intent, records in jeeves.clom._records.items()
        },
        "krem": {
            concept: {
                "strength": cell.strength,
                "reviews": cell.reviews,
                "last_seen": cell.last_seen,
            }
            for concept, cell in jeeves.krem._cells.items()
        },
    }


def restore_matrices(data: Dict[str, Any], jeeves: Any) -> None:
    from skeleton.jeeves.matrices import RetentionCell

    for a, edges in data.get("sam", {}).items():
        for b, w in edges.items():
            jeeves.sam._edges.setdefault(a, {})[b] = w

    for intent, records in data.get("clom", {}).items():
        for r in records:
            jeeves.clom.observe(intent, r["success"], r.get("latency_ms", 0.0))

    for concept, cell in data.get("krem", {}).items():
        jeeves.krem._cells[concept] = RetentionCell(
            concept=concept,
            strength=cell.get("strength", 1.0),
            reviews=cell.get("reviews", 0),
            last_seen=cell.get("last_seen", time.time()),
        )


# --- Whole-system capture ----------------------------------------------

def snapshot_genesis_state(genesis: Any, store: Optional[SnapshotStore] = None, name: str = "genesis") -> Dict[str, Any]:
    """Capture persistable genesis state to disk."""
    store = store or SnapshotStore()
    captured: Dict[str, Any] = {"name": name, "planes": {}}

    rag = genesis.handles.get("rag")
    if rag is not None and hasattr(rag, "_entries"):
        store.save(f"{name}-rag", serialize_vector_store(rag))
        captured["planes"]["rag"] = len(rag._entries)

    mag = genesis.handles.get("mag")
    if mag is not None:
        store.save(f"{name}-mag", serialize_mag(mag))
        captured["planes"]["mag"] = len(mag._episodes)

    quad = genesis.handles.get("quad")
    if quad is not None:
        kag = quad._planes.get("kag")
        if kag is not None:
            store.save(f"{name}-kag", serialize_graph(kag.graph))
            captured["planes"]["kag"] = kag.graph.stats()["triples"]

    return captured


def restore_genesis_state(genesis: Any, store: Optional[SnapshotStore] = None, name: str = "genesis") -> Dict[str, Any]:
    """Restore persistable genesis state from disk."""
    store = store or SnapshotStore()
    restored: Dict[str, int] = {}

    rag_data = store.load(f"{name}-rag")
    rag = genesis.handles.get("rag")
    if rag_data and rag is not None:
        restored["rag"] = restore_vector_store(rag_data, rag)

    mag_data = store.load(f"{name}-mag")
    mag = genesis.handles.get("mag")
    if mag_data and mag is not None:
        restored["mag"] = restore_mag(mag_data, mag)

    kag_data = store.load(f"{name}-kag")
    quad = genesis.handles.get("quad")
    if kag_data and quad is not None:
        kag = quad._planes.get("kag")
        if kag is not None:
            restored["kag"] = restore_graph(kag_data, kag.graph)

    return restored
